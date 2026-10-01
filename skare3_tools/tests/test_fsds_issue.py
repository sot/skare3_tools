"""
Tests for the skare3-fsds-issue script and the Jira client behind it.

Covers:
- the markdown -> Jira wiki converter (skare3_tools.scripts.fsds_issue), including
  truncation of the PR body after the Testing section, the PR -> release wording
  change scoped to the intro, and protection of fenced code blocks,
- the Jira REST client (skare3_tools.jira): token resolution, session headers,
  authentication check, issue creation, search, update, and the create-or-update
  workflow shared by the release-issue scripts (all HTTP stubbed with `responses`),
- the CLI --dry-run path end to end, with the GitHub API stubbed.
"""

import json
from pathlib import Path

import pytest
import responses

from skare3_tools import jira
from skare3_tools.scripts import fsds_issue

DATA_DIR = Path(__file__).parent / "data" / "fsds"
JIRA_URL = "https://occ-cfa.cfa.harvard.edu"


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


def test_truncate_description_keeps_top_interface_impacts_testing():
    body = (
        "# title\n\nintro\n\n## Interface Impacts:\n\nimpacts\n\n"
        "## Testing:\n\n- a test\n\n"
        "## Review\n\nreview text\n\n## Deployment\n\nplan\n\n"
        "# Code changes\n\nstuff\n"
    )
    result = fsds_issue.truncate_description(body)
    assert "intro" in result
    assert "## Interface Impacts:" in result
    assert "impacts" in result
    assert "## Testing:" in result
    assert "- a test" in result
    assert "Review" not in result
    assert "Deployment" not in result
    assert "Code changes" not in result


def test_truncate_description_keeps_subsections_of_testing():
    body = "# title\n\nintro\n\n## Testing:\n\n### details\n\nmore\n\n## Review\n\nx\n"
    result = fsds_issue.truncate_description(body)
    assert "### details" in result
    assert "Review" not in result


def test_truncate_description_without_testing_keeps_interface_impacts():
    body = (
        "# title\n\nintro\n\n## Interface Impacts:\n\nimpacts\n\n"
        "## Review\n\nreview\n\n# Code changes\n\nx\n"
    )
    result = fsds_issue.truncate_description(body)
    assert "intro" in result
    assert "## Interface Impacts:" in result
    assert "impacts" in result
    assert "Review" not in result
    assert "Code changes" not in result


def test_truncate_description_without_wanted_sections_keeps_top(caplog):
    body = "# title\n\nintro\n\n## Review\n\nreview\n\n# Code changes\n\nx\n"
    result = fsds_issue.truncate_description(body)
    assert "title" in result
    assert "intro" in result
    assert "Review" not in result
    assert "Code changes" not in result
    assert "Interface Impacts or Testing" in caplog.text


def test_replace_pr_with_release_intro_only():
    body = (
        "# ska3-flight 2026.9\n\n"
        "This PR includes changes. Another PR word.\n\n"
        "## Testing:\n\nSee the PR for details.\n"
    )
    result = fsds_issue.replace_pr_with_release(body)
    assert "This release includes changes. Another release word." in result
    assert "See the PR for details." in result


def test_markdown_to_jira_headings():
    text = "# one\n## two\n### three\n"
    assert fsds_issue.markdown_to_jira(text) == "h1. one\nh2. two\nh3. three\n"


def test_markdown_to_jira_links_bold_code():
    text = "See [docs](https://example.com/x) and **bold** and `code`.\n"
    expected = "See [docs|https://example.com/x] and *bold* and {{code}}.\n"
    assert fsds_issue.markdown_to_jira(text) == expected


def test_markdown_to_jira_bullets_nested():
    text = "- top\n  - nested\n- other\n"
    assert fsds_issue.markdown_to_jira(text) == "* top\n** nested\n* other\n"


def test_markdown_to_jira_nested_bullet_with_bold():
    # the bold pass must not eat the "**" bullet markers of nested items
    text = "- **pkg:** 1.0 -> 2.0\n  - **sub** item\n"
    expected = "* *pkg:* 1.0 -> 2.0\n** *sub* item\n"
    assert fsds_issue.markdown_to_jira(text) == expected


def test_markdown_to_jira_checklists():
    text = "- [x] done\n- [ ] todo\n"
    assert fsds_issue.markdown_to_jira(text) == "* (/) done\n* todo\n"


def test_markdown_to_jira_protects_code_blocks():
    text = "before\n```\n# not a heading\n**not bold**\n- not a bullet\n```\nafter\n"
    result = fsds_issue.markdown_to_jira(text)
    assert (
        result == "before\n{noformat}\n# not a heading\n**not bold**\n- not a bullet\n"
        "{noformat}\nafter\n"
    )


def test_pr_body_to_jira_description_full():
    body = (DATA_DIR / "pr_body.md").read_text()
    expected = (DATA_DIR / "pr_body.jira").read_text()
    assert fsds_issue.pr_body_to_jira_description(body) == expected


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------


def test_build_fields():
    pr = {
        "title": "2026.9",
        "html_url": "https://github.com/sot/skare3/pull/1696",
        "body": (DATA_DIR / "pr_body.md").read_text(),
    }
    fields = fsds_issue.build_fields("2026.9", pr)
    assert fields["project"] == {"key": "FSDS"}
    assert fields["issuetype"] == {"id": "10700"}
    assert fields["summary"] == "ska3-flight 2026.9"
    assert fields["description"].startswith("h1. ska3-flight 2026.9")
    assert "https://github.com/sot/skare3/pull/1696" in fields["customfield_12000"]
    assert "Testing is detailed" in fields["customfield_12001"]
    assert "Interface impacts are detailed" in fields["customfield_12002"]


# ---------------------------------------------------------------------------
# Jira client
# ---------------------------------------------------------------------------


def test_resolve_token_argument():
    assert jira.resolve_token("abc") == "abc"


def test_resolve_token_from_file(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("secret-token\n")
    assert jira.resolve_token(str(token_file)) == "secret-token"


def test_resolve_token_from_env(monkeypatch):
    monkeypatch.setenv("FSDS_JIRA_TOKEN", "env-token")
    assert jira.resolve_token() == "env-token"


def test_resolve_token_argument_wins_over_env(monkeypatch):
    monkeypatch.setenv("FSDS_JIRA_TOKEN", "env-token")
    assert jira.resolve_token("arg-token") == "arg-token"


def test_resolve_token_missing(monkeypatch):
    monkeypatch.delenv("FSDS_JIRA_TOKEN", raising=False)
    assert jira.resolve_token() is None


def test_get_session_headers():
    session = jira.get_session(token="abc")
    assert session.headers["Authorization"] == "Bearer abc"
    assert session.headers["X-Atlassian-Token"] == "no-check"


def test_get_session_without_token_raises(monkeypatch):
    monkeypatch.delenv("FSDS_JIRA_TOKEN", raising=False)
    with pytest.raises(jira.JiraAuthError, match="FSDS_JIRA_TOKEN"):
        jira.get_session()


@responses.activate
def test_verify():
    responses.add(
        responses.GET,
        f"{JIRA_URL}/rest/api/2/myself",
        json={"name": "jgonzalez", "displayName": "Javier Gonzalez"},
        status=200,
    )
    session = jira.get_session(token="abc")
    user = jira.verify(session, url=JIRA_URL)
    assert user["displayName"] == "Javier Gonzalez"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer abc"


@responses.activate
def test_verify_bad_token():
    responses.add(responses.GET, f"{JIRA_URL}/rest/api/2/myself", status=401)
    session = jira.get_session(token="bad")
    with pytest.raises(jira.JiraAuthError):
        jira.verify(session, url=JIRA_URL)


@responses.activate
def test_create_issue():
    responses.add(
        responses.POST,
        f"{JIRA_URL}/rest/api/2/issue",
        json={"id": "1", "key": "FSDS-1234", "self": f"{JIRA_URL}/rest/api/2/issue/1"},
        status=201,
    )
    session = jira.get_session(token="abc")
    fields = {"summary": "ska3-flight 2026.9"}
    result = jira.create_issue(session, fields, url=JIRA_URL)
    assert result["key"] == "FSDS-1234"
    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer abc"
    assert request.headers["X-Atlassian-Token"] == "no-check"
    assert json.loads(request.body) == {"fields": fields}


@responses.activate
def test_create_issue_error_reports_jira_message():
    responses.add(
        responses.POST,
        f"{JIRA_URL}/rest/api/2/issue",
        json={"errorMessages": [], "errors": {"summary": "Summary is required."}},
        status=400,
    )
    session = jira.get_session(token="abc")
    with pytest.raises(jira.JiraError, match="Summary is required"):
        jira.create_issue(session, {}, url=JIRA_URL)


SEARCH_URL = f"{JIRA_URL}/rest/api/2/search"

FIELDS = {
    "project": {"key": "MATLAB"},
    "issuetype": {"id": "10101"},
    "summary": "Python updates for ska3-matlab (Release 2026_060)",
    "description": "intro\n\nsummary\n",
    "customfield_11600": "2026_060",
    "customfield_11900": [{"name": "jdoe"}],
}


def _issue(key="MATLAB-12345", status="Not Started", **fields):
    """An issue as returned by the Jira search, with the fields of FIELDS by default."""
    issue_fields = {
        "summary": FIELDS["summary"],
        "status": {"name": status, "id": "1"},
        # as Jira returns them: CRLF line ends, full user objects
        "description": FIELDS["description"].replace("\n", "\r\n"),
        "customfield_11600": FIELDS["customfield_11600"],
        "customfield_11900": [{"name": "jdoe", "key": "jdoe", "displayName": "J. Doe"}],
    }
    issue_fields.update(fields)
    return {"key": key, "fields": issue_fields}


def _stub_search(issues):
    responses.add(responses.GET, SEARCH_URL, json={"issues": issues})


@responses.activate
def test_find_issue_exact_summary():
    # the JQL text search also returns issues with a similar summary
    _stub_search([_issue("MATLAB-1", summary=FIELDS["summary"] + " (copy)"), _issue()])
    session = jira.get_session(token="abc")
    issue = jira.find_issue(session, "MATLAB", FIELDS["summary"], url=JIRA_URL)
    assert issue["key"] == "MATLAB-12345"
    jql = responses.calls[0].request.params["jql"]
    assert jql == f'project = MATLAB AND summary ~ "\\"{FIELDS["summary"]}\\""'


@responses.activate
def test_find_issue_none():
    _stub_search([])
    session = jira.get_session(token="abc")
    assert jira.find_issue(session, "MATLAB", FIELDS["summary"], url=JIRA_URL) is None


@responses.activate
def test_find_issue_more_than_one():
    _stub_search([_issue("MATLAB-1"), _issue("MATLAB-2")])
    session = jira.get_session(token="abc")
    with pytest.raises(jira.JiraError, match="MATLAB-1, MATLAB-2"):
        jira.find_issue(session, "MATLAB", FIELDS["summary"], url=JIRA_URL)


@responses.activate
def test_update_issue_omits_project_and_issuetype():
    responses.add(
        responses.PUT, f"{JIRA_URL}/rest/api/2/issue/MATLAB-12345", status=204
    )
    session = jira.get_session(token="abc")
    jira.update_issue(session, "MATLAB-12345", FIELDS, url=JIRA_URL)
    sent = json.loads(responses.calls[0].request.body)["fields"]
    assert "project" not in sent
    assert "issuetype" not in sent
    assert sent["summary"] == FIELDS["summary"]


@responses.activate
def test_update_issue_error_reports_jira_message():
    responses.add(
        responses.PUT,
        f"{JIRA_URL}/rest/api/2/issue/MATLAB-12345",
        json={"errorMessages": [], "errors": {"customfield_11600": "not on screen"}},
        status=400,
    )
    session = jira.get_session(token="abc")
    with pytest.raises(jira.JiraError, match="not on screen"):
        jira.update_issue(session, "MATLAB-12345", FIELDS, url=JIRA_URL)


def test_field_changes_ignores_jira_formatting():
    # CRLF line ends and full user objects are not changes
    assert jira.field_changes(_issue()["fields"], FIELDS) == {}


def test_field_changes():
    current = _issue(description="old\r\n", customfield_11900=None)["fields"]
    assert jira.field_changes(current, FIELDS) == {
        "description": ("old", "intro\n\nsummary"),
        "customfield_11900": (None, ["jdoe"]),
    }


def test_format_changes():
    text = jira.format_changes(
        {"description": ("a\nb", "a\nc"), "customfield_11600": ("2026_050", "2026_060")}
    )
    assert "--- description (current)" in text
    assert "-b\n+c" in text
    assert "customfield_11600: '2026_050' -> '2026_060'" in text


def _create_or_update(**kwargs):
    session = jira.get_session(token="abc")
    jira.create_or_update_issue(
        session, FIELDS, locked_statuses=("Resolved",), url=JIRA_URL, **kwargs
    )


def _writes():
    return [c.request.method for c in responses.calls if c.request.method != "GET"]


@responses.activate
def test_create_or_update_creates(capsys):
    _stub_search([])
    responses.add(
        responses.POST, f"{JIRA_URL}/rest/api/2/issue", json={"key": "MATLAB-12345"}
    )
    _create_or_update()
    assert _writes() == ["POST"]
    assert "Created MATLAB-12345" in capsys.readouterr().out


@responses.activate
def test_create_or_update_dry_run_does_not_create(capsys):
    _stub_search([])
    _create_or_update(dry_run=True)
    assert _writes() == []
    assert "would be created" in capsys.readouterr().out


@responses.activate
def test_create_or_update_up_to_date(capsys):
    _stub_search([_issue()])
    _create_or_update(update=True)
    assert _writes() == []
    assert "MATLAB-12345 (Not Started) is up to date" in capsys.readouterr().out


@responses.activate
def test_create_or_update_differs_without_update(capsys):
    _stub_search([_issue(description="old")])
    with pytest.raises(jira.JiraError, match="Use --update"):
        _create_or_update()
    assert _writes() == []
    out = capsys.readouterr().out
    assert "MATLAB-12345 (Not Started) differs" in out
    assert "+intro" in out


@responses.activate
def test_create_or_update_differs_dry_run(capsys):
    _stub_search([_issue(description="old")])
    _create_or_update(update=True, dry_run=True)
    assert _writes() == []
    assert "+intro" in capsys.readouterr().out


@responses.activate
def test_create_or_update_updates(capsys):
    _stub_search([_issue(description="old")])
    responses.add(
        responses.PUT, f"{JIRA_URL}/rest/api/2/issue/MATLAB-12345", status=204
    )
    _create_or_update(update=True)
    assert _writes() == ["PUT"]
    assert "Updated MATLAB-12345" in capsys.readouterr().out


@responses.activate
def test_create_or_update_locked_status():
    _stub_search([_issue(status="Resolved", description="old")])
    with pytest.raises(jira.JiraError, match="is Resolved .* --force"):
        _create_or_update(update=True)
    assert _writes() == []


@responses.activate
def test_create_or_update_locked_status_force():
    _stub_search([_issue(status="Resolved", description="old")])
    responses.add(
        responses.PUT, f"{JIRA_URL}/rest/api/2/issue/MATLAB-12345", status=204
    )
    _create_or_update(update=True, force=True)
    assert _writes() == ["PUT"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _stub_github(rsps, pulls):
    rsps.add(responses.GET, "https://api.github.com/", json={}, status=200)
    rsps.add(
        responses.GET,
        "https://api.github.com/user",
        json={"login": "tester"},
        status=200,
    )
    rsps.add(
        responses.POST,
        "https://api.github.com/graphql",
        json={"data": {"viewer": {"login": "tester"}}},
        status=200,
    )
    rsps.add(
        responses.GET,
        "https://api.github.com/repos/sot/skare3",
        json={"name": "skare3"},
        status=200,
    )
    # paginated list: one page of results, then an empty page
    rsps.add(responses.GET, "https://api.github.com/repos/sot/skare3/pulls", json=pulls)
    rsps.add(responses.GET, "https://api.github.com/repos/sot/skare3/pulls", json=[])


def _pr(number=1696, title="2026.9"):
    return {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/sot/skare3/pull/{number}",
        "body": (DATA_DIR / "pr_body.md").read_text(),
    }


@responses.activate
def test_main_dry_run(monkeypatch, capsys):
    _stub_github(responses, [_pr()])
    monkeypatch.setattr(
        "sys.argv",
        ["skare3-fsds-issue", "2026.9", "--dry-run", "--github-token", "test-token"],
    )
    fsds_issue.main()
    out = capsys.readouterr().out
    assert "h1. ska3-flight 2026.9" in out
    assert '"summary": "ska3-flight 2026.9"' in out
    assert "https://github.com/sot/skare3/pull/1696" in out
    # no Jira request fired (responses would raise ConnectionError on any
    # un-stubbed request, and all recorded calls are to the GitHub API)
    assert all("api.github.com" in c.request.url for c in responses.calls)


@responses.activate
def test_main_no_matching_pr_exits(monkeypatch, capsys):
    _stub_github(responses, [_pr(title="unrelated PR")])
    monkeypatch.setattr(
        "sys.argv",
        ["skare3-fsds-issue", "2026.9", "--dry-run", "--github-token", "test-token"],
    )
    with pytest.raises(SystemExit):
        fsds_issue.main()


@responses.activate
def test_main_ambiguous_pr_exits(monkeypatch, capsys):
    _stub_github(responses, [_pr(1696, "2026.9"), _pr(1700, "revert 2026.9")])
    monkeypatch.setattr(
        "sys.argv",
        ["skare3-fsds-issue", "2026.9", "--dry-run", "--github-token", "test-token"],
    )
    with pytest.raises(SystemExit) as excinfo:
        fsds_issue.main()
    assert excinfo.value.code != 0
    assert "1700" in capsys.readouterr().err


@responses.activate
@pytest.mark.parametrize("version,number", [("2026.1", 1690), ("2026.13", 1733)])
def test_find_pr_matches_whole_version(version, number):
    _stub_github(responses, [_pr(1733, "2026.13"), _pr(1690, "ska3-flight 2026.1")])
    fsds_issue.github.init(token="test-token")
    assert fsds_issue.find_pr(version)["number"] == number


@responses.activate
def test_main_approved_issue_is_not_updated(monkeypatch, capsys):
    _stub_github(responses, [_pr()])
    responses.add(responses.GET, f"{JIRA_URL}/rest/api/2/myself", json={"name": "jdoe"})
    existing = {
        "key": "FSDS-215",
        "fields": {"summary": "ska3-flight 2026.9", "status": {"name": "Approved"}},
    }
    responses.add(responses.GET, SEARCH_URL, json={"issues": [existing]})
    monkeypatch.setattr(
        "sys.argv",
        [
            "skare3-fsds-issue",
            "2026.9",
            "--update",
            "--token",
            "abc",
            "--github-token",
            "x",
        ],
    )
    with pytest.raises(SystemExit, match="FSDS-215 is Approved"):
        fsds_issue.main()
    assert "FSDS-215 (Approved) differs" in capsys.readouterr().out
    assert not any(
        c.request.method in ("POST", "PUT")
        for c in responses.calls
        if c.request.url.startswith(JIRA_URL)
    )
