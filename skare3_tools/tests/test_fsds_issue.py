"""
Tests for the skare3-fsds-issue script and the Jira client behind it.

Covers:
- the markdown -> Jira wiki converter (skare3_tools.scripts.fsds_issue), including
  truncation of the PR body after the Testing section, the PR -> release wording
  change scoped to the intro, and protection of fenced code blocks,
- the Jira REST client (skare3_tools.jira): token resolution, session headers,
  authentication check, and issue creation (all HTTP stubbed with `responses`),
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
