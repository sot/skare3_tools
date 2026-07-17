"""
Minimal client for the OCC Jira server (FSDS project).

Authentication uses a Jira Personal Access Token, created once at
https://occ-cfa.cfa.harvard.edu (avatar -> Profile -> Personal Access Tokens).
The token is passed as an argument (the value itself or the path to a file
containing it) or through the FSDS_JIRA_TOKEN environment variable.
"""

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
