"""
Minimal client for the OCC Jira server (FSDS and MATLAB projects).

Authentication uses a Jira Personal Access Token, created once at
https://occ-cfa.cfa.harvard.edu (avatar -> Profile -> Personal Access Tokens).
The token is passed as an argument (the value itself or the path to a file
containing it) or through the FSDS_JIRA_TOKEN environment variable.

`create_or_update_issue` is the workflow shared by the release-issue scripts:
an issue is identified by its project and summary, so running a script again
for the same release finds the issue it created before.
"""

import difflib
import os
from pathlib import Path

import requests

JIRA_URL = "https://occ-cfa.cfa.harvard.edu"

TOKEN_HELP = (
    "No Jira token found. Create a Personal Access Token at "
    f"{JIRA_URL} (avatar -> Profile -> Personal Access Tokens) and pass it "
    "with --token or set the FSDS_JIRA_TOKEN environment variable."
)


class JiraError(Exception):
    pass


class JiraAuthError(JiraError):
    pass


def resolve_token(token=None):
    """
    Resolve the Jira Personal Access Token.

    :param token: str (optional)
        The token itself, or the path to a file containing it. If not given,
        the FSDS_JIRA_TOKEN environment variable is used.
    :return: str or None
    """
    if token is None:
        token = os.environ.get("FSDS_JIRA_TOKEN")
    elif Path(token).exists():
        token = Path(token).read_text().strip()
    return token


def get_session(token=None):
    """
    Return a requests.Session authenticated with a Personal Access Token.

    :param token: str (optional)
        Token value or token file path (see `resolve_token`).
    :return: requests.Session
    """
    token = resolve_token(token)
    if token is None:
        raise JiraAuthError(TOKEN_HELP)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    session.headers["X-Atlassian-Token"] = "no-check"
    return session


def verify(session, url=JIRA_URL):
    """
    Check that the session is authenticated.

    :param session: requests.Session
    :param url: str
    :return: dict
        The authenticated user (GET /rest/api/2/myself).
    """
    response = session.get(f"{url}/rest/api/2/myself")
    if not response.ok:
        raise JiraAuthError(
            f"Jira authentication failed ({response.status_code}). {TOKEN_HELP}"
        )
    return response.json()


def create_issue(session, fields, url=JIRA_URL):
    """
    Create a Jira issue.

    :param session: requests.Session
    :param fields: dict
        Issue fields (project, issuetype, summary, description, ...).
    :param url: str
    :return: dict
        The Jira response ({"id": ..., "key": ..., "self": ...}).
    """
    response = session.post(f"{url}/rest/api/2/issue", json={"fields": fields})
    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise JiraError(
            f"Jira issue creation failed ({response.status_code}): {detail}"
        )
    return response.json()


def update_issue(session, key, fields, url=JIRA_URL):
    """
    Update the fields of an existing Jira issue.

    The project and the issue type cannot be changed this way, so they are not sent.

    :param session: requests.Session
    :param key: str
        Issue key (e.g. "MATLAB-12322").
    :param fields: dict
        Issue fields, as given to `create_issue`.
    :param url: str
    """
    fields = {k: v for k, v in fields.items() if k not in ("project", "issuetype")}
    response = session.put(f"{url}/rest/api/2/issue/{key}", json={"fields": fields})
    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise JiraError(
            f"Jira update of {key} failed ({response.status_code}): {detail}"
        )


def find_issue(session, project, summary, fields=(), url=JIRA_URL):
    """
    Find the issue in a project with exactly this summary.

    :param session: requests.Session
    :param project: str
        Project key (e.g. "MATLAB").
    :param summary: str
    :param fields: list of str
        Fields to return, in addition to summary and status.
    :param url: str
    :return: dict or None
        The issue ({"key": ..., "fields": {...}}), or None if there is none.
    """
    # The JQL "~" operator is a fuzzy text search, so the summary is checked here.
    phrase = summary.replace("\\", "\\\\").replace('"', '\\"')
    params = {
        "jql": f'project = {project} AND summary ~ "\\"{phrase}\\""',
        "fields": ",".join(["summary", "status", *fields]),
    }
    response = session.get(f"{url}/rest/api/2/search", params=params)
    if not response.ok:
        raise JiraError(f"Jira search failed ({response.status_code}): {response.text}")
    issues = [
        issue
        for issue in response.json()["issues"]
        if issue["fields"]["summary"] == summary
    ]
    if len(issues) > 1:
        keys = ", ".join(issue["key"] for issue in issues)
        raise JiraError(
            f"More than one {project} issue has summary '{summary}': {keys}"
        )
    return issues[0] if issues else None


def _simplify(value):
    """Reduce a Jira field value to what identifies it (user name, option value, ...)."""
    if isinstance(value, list):
        return [_simplify(item) for item in value]
    if isinstance(value, dict):
        for name in ("name", "value", "key", "id"):
            if name in value:
                return value[name]
    if isinstance(value, str):
        return value.replace("\r\n", "\n").strip()
    return value


def field_changes(current, new):
    """
    Get the fields that differ between an issue's current fields and new ones.

    :param current: dict
        The issue's current fields (as returned by Jira).
    :param new: dict
        The new fields (as given to `create_issue`).
    :return: dict
        {field name: (current value, new value)}, values simplified for comparison.
    """
    changes = {}
    for name, value in new.items():
        if name in ("project", "issuetype"):
            continue
        old = _simplify(current.get(name))
        value = _simplify(value)
        if old != value:
            changes[name] = (old, value)
    return changes


def format_changes(changes):
    """Format `field_changes` output for people: a diff for text, old -> new otherwise."""
    lines = []
    for name, (old, new) in changes.items():
        if isinstance(old, str) and isinstance(new, str) and "\n" in old + new:
            diff = difflib.unified_diff(
                old.splitlines(), new.splitlines(), f"{name} (current)", f"{name} (new)"
            )
            lines.extend(line.rstrip("\n") for line in diff)
        else:
            lines.append(f"{name}: {old!r} -> {new!r}")
    return "\n".join(lines)


def create_or_update_issue(
    session,
    fields,
    locked_statuses=(),
    update=False,
    force=False,
    dry_run=False,
    url=JIRA_URL,
):
    """
    Create an issue, or report or update the existing issue with the same summary.

    - No such issue: create it.
    - The issue exists and matches `fields`: nothing to do.
    - The issue exists and differs: print the changes. Update it only with
      `update`, and only if its status is not in `locked_statuses` (unless `force`).

    With `dry_run`, nothing is created or updated. Results are printed.

    :param session: requests.Session
    :param fields: dict
        Issue fields, as given to `create_issue`.
    :param locked_statuses: list of str
        Statuses in which the issue is not updated without `force`.
    :param update: bool
    :param force: bool
    :param dry_run: bool
    :param url: str
    :raises JiraError: if the issue differs and is not updated.
    """
    project = fields["project"]["key"]
    issue = find_issue(
        session, project, fields["summary"], fields=list(fields), url=url
    )
    if issue is None:
        if dry_run:
            print(f"No {project} issue '{fields['summary']}' yet. It would be created.")
            return
        result = create_issue(session, fields, url=url)
        print(f"Created {result['key']}: {url}/browse/{result['key']}")
        return

    key = issue["key"]
    status = issue["fields"]["status"]["name"]
    changes = field_changes(issue["fields"], fields)
    if not changes:
        print(f"{key} ({status}) is up to date: {url}/browse/{key}")
        return
    print(f"{key} ({status}) differs from the release: {url}/browse/{key}")
    print(format_changes(changes))
    if dry_run:
        return
    if not update:
        raise JiraError(f"{key} already exists. Use --update to update it.")
    if status in locked_statuses and not force:
        raise JiraError(
            f"{key} is {status} and is not updated. Use --force to update it anyway."
        )
    update_issue(session, key, fields, url=url)
    print(f"Updated {key}: {url}/browse/{key}")
