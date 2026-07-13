"""
Authentication helpers for the skare3 GitHub App (App ID 77359).

The App's private key is read from the path in the ``SKARE3_GITHUB_APP_KEY``
environment variable (or an explicit ``key_path`` argument). The organization
acted on by default is taken from the ``SKARE3_GITHUB_APP_ORG`` environment
variable.
"""

import os
import time

import requests

APP_ID = 77359
GITHUB_API = "https://api.github.com"


def app_settings():
    """
    GitHub App auth settings, read from the environment.

    This is the single place where the App environment variables are read,
    so the source can change later (e.g. a config file) without touching
    callers.
    """
    return {
        "app_id": APP_ID,
        "key_path": os.environ.get("SKARE3_GITHUB_APP_KEY"),
        "org": os.environ.get("SKARE3_GITHUB_APP_ORG"),
    }


def _read_key(key_path=None):
    key_path = key_path or app_settings()["key_path"]
    if not key_path:
        raise ValueError(
            "No GitHub App key: pass key_path or set SKARE3_GITHUB_APP_KEY"
        )
    with open(key_path, "rb") as fh:
        return fh.read()


def github_app_token(key_path=None):
    """Return a short-lived JWT identifying the GitHub App."""
    # pyjwt/cryptography are only needed for App auth, and this module is
    # imported from github.py's init; import lazily so personal-token users
    # do not need them installed.
    import jwt

    now = int(time.time())
    # PyJWT >= 2.10 requires the "iss" claim to be a string; APP_ID stays an
    # int constant (matching GitHub's own docs) and is stringified here.
    payload = {"iat": now, "exp": now + 10 * 60, "iss": str(APP_ID)}
    return jwt.encode(payload, _read_key(key_path), algorithm="RS256")


def _app_headers(key_path=None):
    return {
        "Authorization": f"Bearer {github_app_token(key_path)}",
        "Accept": "application/vnd.github+json",
    }


def get_app_info(key_path=None):
    """Return the App's own metadata (sanity check for key + App ID)."""
    r = requests.get(f"{GITHUB_API}/app", headers=_app_headers(key_path))
    r.raise_for_status()
    return r.json()


def get_installations(key_path=None):
    """List the App's installations (e.g. to find an installation id)."""
    r = requests.get(f"{GITHUB_API}/app/installations", headers=_app_headers(key_path))
    r.raise_for_status()
    return r.json()


def get_installation_token(installation_id, key_path=None):
    """Mint an installation access token (dict with 'token', 'expires_at')."""
    r = requests.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers=_app_headers(key_path),
    )
    r.raise_for_status()
    return r.json()


def get_repositories(token):
    """List repositories accessible to an installation token."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    r = requests.get(f"{GITHUB_API}/installation/repositories", headers=headers)
    r.raise_for_status()
    return r.json()
