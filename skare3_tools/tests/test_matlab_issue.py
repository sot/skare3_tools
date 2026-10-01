"""
Tests for the skare3-matlab-issue script.

Covers:
- extraction of the executive summary from the release PR description,
- the issue description and fields,
- the Matlab Tools release lookup from the sot/skare3 milestones,
- the CLI (--dry-run and issue creation), with the GitHub and Jira APIs stubbed.

The Jira client itself is tested in test_fsds_issue.py.
"""

import json
from pathlib import Path

import pytest
import responses

from skare3_tools import github
from skare3_tools.scripts import matlab_issue

DATA_DIR = Path(__file__).parent / "data" / "matlab"
JIRA_URL = "https://occ-cfa.cfa.harvard.edu"
MILESTONES_URL = "https://api.github.com/repos/sot/skare3/milestones"

MILESTONE_TITLES = [
    "2019-Feb MATLAB",
    "2026.8 (MATLAB 2026_030)",
    "2026.13 (MATLAB 2026_060)",
    "2026.14",
]


def _pr(number=1733, title="2026.13"):
    return {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/sot/skare3/pull/{number}",
        "body": (DATA_DIR / "pr_body.md").read_text(),
        "milestone": None,
    }


# ---------------------------------------------------------------------------
# Description
# ---------------------------------------------------------------------------


def test_executive_summary_stops_at_first_section():
    body = "# ska3-matlab 2026.13\n\nThis PR includes:\n- kadi\n\n## Interface Impacts:\n\nx\n"
    assert matlab_issue.executive_summary(body) == "This PR includes:\n- kadi"


def test_executive_summary_without_title():
    body = "This PR includes:\n- kadi\n\n## Testing:\n\nx\n"
    assert matlab_issue.executive_summary(body) == "This PR includes:\n- kadi"


def test_executive_summary_ignores_headings_in_code():
    body = "# title\n\nsummary\n```\n# not a heading\n```\n\n## Testing:\n"
    assert matlab_issue.executive_summary(body) == "summary\n```\n# not a heading\n```"


def test_executive_summary_missing(caplog):
    body = "# ska3-matlab 2026.13\n\n## Interface Impacts:\n\nx\n"
    assert matlab_issue.executive_summary(body) == ""
    assert "No executive summary" in caplog.text


def test_build_description():
    description = matlab_issue.build_description("2026.13", "2026_060", _pr())
    assert description == (DATA_DIR / "description.jira").read_text()


def test_build_description_without_summary():
    pr = _pr()
    pr["body"] = None
    description = matlab_issue.build_description("2026.13", "2026_060", pr)
    assert description == (
        "The ska3 release for 2026_060 will be 2026.13. "
        "This is the corresponding PR: [https://github.com/sot/skare3/pull/1733]\n"
    )


def test_build_fields():
    fields = matlab_issue.build_fields("2026.13", "2026_060", _pr())
    assert fields == {
        "project": {"key": "MATLAB"},
        "issuetype": {"id": "10101"},
        "summary": "Python updates for ska3-matlab (Release 2026_060)",
        "description": (DATA_DIR / "description.jira").read_text(),
        "customfield_11600": "2026_060",
    }


def test_build_fields_with_developer():
    fields = matlab_issue.build_fields("2026.13", "2026_060", _pr(), developer="jdoe")
    assert fields["customfield_11900"] == [{"name": "jdoe"}]
    assert "assignee" not in fields


# ---------------------------------------------------------------------------
# Matlab release lookup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,expected",
    [
        ("2026.13 (MATLAB 2026_060)", ("2026.13", "2026_060")),
        ("2026.13 MATLAB 2026_060", ("2026.13", "2026_060")),
        ("2026.13", ("2026.13", None)),
        ("MATLAB 2026_060", (None, "2026_060")),
        ("(Matlab 2026_060)", (None, "2026_060")),
        (" 2026.13 ", ("2026.13", None)),
        ("2019-Feb MATLAB", (None, None)),
        ("2026.13rc1", (None, None)),
    ],
)
def test_parse_milestone_title(title, expected):
    assert matlab_issue.parse_milestone_title(title) == expected


@pytest.fixture()
def github_api(monkeypatch):
    monkeypatch.setattr(github.GITHUB_API_V3, "initialized", True)
    monkeypatch.setattr(github.GITHUB_API_V3, "auth", None)


def _stub_milestones(rsps, milestones):
    rsps.add(responses.GET, "https://api.github.com/repos/sot/skare3", json={"name": "skare3"})
    # paginated list: one page of results, then an empty page
    rsps.add(responses.GET, MILESTONES_URL, json=milestones)
    rsps.add(responses.GET, MILESTONES_URL, json=[])


def _milestones(*titles):
    return [{"number": i, "title": title} for i, title in enumerate(titles)]


@responses.activate
@pytest.mark.parametrize(
    "titles,version,matlab_release,expected",
    [
        # the proper title, among others
        (MILESTONE_TITLES, "2026.13", None, "2026_060"),
        (MILESTONE_TITLES, "2026.8", None, "2026_030"),
        # the given release agrees with the title
        (MILESTONE_TITLES, "2026.13", "2026_060", "2026_060"),
        # title without the Matlab release
        (["2026.13"], "2026.13", "2026_060", "2026_060"),
        # title without the version, found from the Matlab release
        (["MATLAB 2026_060"], "2026.13", "2026_060", "2026_060"),
    ],
)
def test_get_matlab_release(github_api, titles, version, matlab_release, expected):
    _stub_milestones(responses, _milestones(*titles))
    assert matlab_issue.get_matlab_release(version, matlab_release) == expected


@responses.activate
@pytest.mark.parametrize(
    "titles,version,matlab_release,message",
    [
        # "2026.1" is not "2026.13"
        (MILESTONE_TITLES, "2026.1", None, "No milestone"),
        # "MATLAB 2026_060" can only be found with the Matlab release
        (["MATLAB 2026_060"], "2026.13", None, "No milestone"),
        (["2026.13"], "2026.13", None, "does not name the Matlab Tools release"),
        (["2026.13 (MATLAB 2026_060)"], "2026.13", "2026_070", "not for MATLAB 2026_070"),
        (["2026.14 (MATLAB 2026_060)"], "2026.13", "2026_060", "not for version 2026.13"),
        (["2026.13", "MATLAB 2026_060"], "2026.13", "2026_060", "More than one"),
    ],
)
def test_get_matlab_release_exits(github_api, titles, version, matlab_release, message):
    _stub_milestones(responses, _milestones(*titles))
    with pytest.raises(SystemExit, match=message):
        matlab_issue.get_matlab_release(version, matlab_release)


def test_get_matlab_release_from_pr_milestone():
    # the PR's milestone is used without listing the milestones (no HTTP stubs)
    pr = _pr()
    pr["milestone"] = {"title": "2026.13 (MATLAB 2026_060)"}
    assert matlab_issue.get_matlab_release("2026.13", pr=pr) == "2026_060"


def test_get_matlab_release_pr_milestone_for_another_version():
    pr = _pr()
    pr["milestone"] = {"title": "2026.10 (MATLAB 2026_040)"}
    with pytest.raises(SystemExit, match="not for version 2026.13"):
        matlab_issue.get_matlab_release("2026.13", pr=pr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _stub_github(rsps, pulls, milestone_titles=MILESTONE_TITLES):
    rsps.add(responses.GET, "https://api.github.com/", json={}, status=200)
    rsps.add(responses.GET, "https://api.github.com/user", json={"login": "tester"})
    rsps.add(
        responses.POST,
        "https://api.github.com/graphql",
        json={"data": {"viewer": {"login": "tester"}}},
    )
    rsps.add(responses.GET, "https://api.github.com/repos/sot/skare3", json={"name": "skare3"})
    # paginated list: one page of results, then an empty page
    rsps.add(responses.GET, "https://api.github.com/repos/sot/skare3/pulls", json=pulls)
    rsps.add(responses.GET, "https://api.github.com/repos/sot/skare3/pulls", json=[])
    _stub_milestones(rsps, _milestones(*milestone_titles))


def _argv(*args):
    return ["skare3-matlab-issue", "2026.13", "--github-token", "test-token", *args]


@responses.activate
def test_main_dry_run(monkeypatch, capsys):
    _stub_github(responses, [_pr()])
    monkeypatch.setattr("sys.argv", _argv("--dry-run"))
    matlab_issue.main()
    out = capsys.readouterr().out
    assert out.startswith((DATA_DIR / "description.jira").read_text())
    assert '"summary": "Python updates for ska3-matlab (Release 2026_060)"' in out
    assert "customfield_11900" not in out
    assert all("api.github.com" in c.request.url for c in responses.calls)


@responses.activate
def test_main_dry_run_matlab_release_option(monkeypatch, capsys):
    _stub_github(responses, [_pr()], milestone_titles=["2026.13"])
    monkeypatch.setattr("sys.argv", _argv("--dry-run", "--matlab-release", "2026_060"))
    matlab_issue.main()
    assert '"customfield_11600": "2026_060"' in capsys.readouterr().out


@responses.activate
def test_main_without_milestone_exits(monkeypatch):
    _stub_github(responses, [_pr()], milestone_titles=[])
    monkeypatch.setattr("sys.argv", _argv("--dry-run", "--matlab-release", "2026_060"))
    with pytest.raises(SystemExit, match="No milestone"):
        matlab_issue.main()


@responses.activate
def test_main_creates_issue(monkeypatch, capsys):
    _stub_github(responses, [_pr()])
    responses.add(
        responses.GET,
        f"{JIRA_URL}/rest/api/2/myself",
        json={"name": "jdoe", "displayName": "J. Doe"},
    )
    responses.add(
        responses.POST,
        f"{JIRA_URL}/rest/api/2/issue",
        json={"id": "1", "key": "MATLAB-12345", "self": "x"},
        status=201,
    )
    monkeypatch.setattr("sys.argv", _argv("--token", "abc"))
    matlab_issue.main()

    posted = json.loads(responses.calls[-1].request.body)["fields"]
    assert posted["project"] == {"key": "MATLAB"}
    assert posted["customfield_11600"] == "2026_060"
    assert posted["customfield_11900"] == [{"name": "jdoe"}]
    assert "assignee" not in posted
    out = capsys.readouterr().out
    assert f"Created MATLAB-12345: {JIRA_URL}/browse/MATLAB-12345" in out
