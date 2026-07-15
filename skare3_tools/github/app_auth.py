"""
Authentication helpers for the skare3 GitHub App (App ID 77359).

The App's private key comes from the ``SKARE3_GITHUB_APP_KEY`` environment
variable (or an explicit ``key_path`` argument), which holds either the path
to the key file or the PEM content itself. Path is the mode for hosts with a
deployed key file; content is the mode for GitHub-hosted runners, where the
key rides in as an Actions secret (note that the self-hosted runner ``.env``
file is line-based and cannot carry a multiline PEM — use a path there).
The organization acted on by default is "sot", overridable with the
``SKARE3_GITHUB_APP_ORG`` environment variable.
"""

import os
import time
from datetime import datetime, timezone

import requests

APP_ID = 77359
GITHUB_API = "https://api.github.com"

# org used for requests that do not name one (e.g. GraphQL calls without an
# org argument); SKARE3_GITHUB_APP_ORG overrides it. Requests that do name an
# org (like most REST endpoints) route to that org regardless.
_SKARE3_GITHUB_APP_ORG = "sot"


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
        "org": os.environ.get("SKARE3_GITHUB_APP_ORG", _SKARE3_GITHUB_APP_ORG),
    }


def _read_key(key_path=None):
    key = key_path or app_settings()["key_path"]
    if not key:
        raise ValueError(
            "No GitHub App key: pass key_path or set SKARE3_GITHUB_APP_KEY"
        )
    if "-----BEGIN" in key:
        # the value is the key itself, not a path (e.g. an Actions secret).
        # PEMs passed through environment variables often arrive with literal
        # "\n" sequences or CRLF line endings; normalize both.
        return key.replace("\\n", "\n").replace("\r\n", "\n").encode()
    try:
        with open(key, "rb") as fh:
            return fh.read()
    except OSError as err:
        raise _auth_exception(f"Cannot read GitHub App key at '{key}': {err}") from err


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
    key = _read_key(key_path)
    try:
        return jwt.encode(payload, key, algorithm="RS256")
    except (ValueError, TypeError, jwt.exceptions.PyJWTError) as err:
        raise _auth_exception(
            f"Invalid GitHub App private key (key_path/SKARE3_GITHUB_APP_KEY): {err}"
        ) from err


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


class AppTokenCache:
    """
    GitHub App installation tokens, minted on demand and cached per organization.

    Installation tokens are scoped to one organization, so a process that
    touches several organizations needs one token per organization. The App
    installation for an organization is looked up the first time it is seen,
    and tokens are re-minted shortly before they expire (they last one hour).
    """

    EXPIRY_MARGIN = 300  # seconds; re-mint a token this close to its expiry

    def __init__(self, key_path=None):
        self.key_path = key_path or app_settings()["key_path"]
        self._installations = {}  # org name -> installation id
        self._tokens = {}  # org name -> {"token": str, "expires_at": datetime}

    def token(self, org=None):
        """Return a valid installation token for org (the default org if None)."""
        if org is None:
            org = self.default_org()
        entry = self._tokens.get(org)
        if entry is None or self._expiring(entry):
            entry = self._mint(org)
            self._tokens[org] = entry
        return entry["token"]

    def default_org(self):
        """The org acted on when a request does not determine one."""
        return app_settings()["org"]

    def _expiring(self, entry):
        remaining = entry["expires_at"] - datetime.now(timezone.utc)
        return remaining.total_seconds() < self.EXPIRY_MARGIN

    def _mint(self, org):
        info = get_installation_token(
            self._installation_id(org), key_path=self.key_path
        )
        return {
            "token": info["token"],
            "expires_at": datetime.fromisoformat(
                info["expires_at"].replace("Z", "+00:00")
            ),
        }

    def _installation_id(self, org):
        if org not in self._installations:
            # repositories can be owned by an organization or by a user account
            for account_type in ["orgs", "users"]:
                r = requests.get(
                    f"{GITHUB_API}/{account_type}/{org}/installation",
                    headers=_app_headers(self.key_path),
                )
                if r.ok:
                    self._installations[org] = r.json()["id"]
                    break
                if r.status_code != 404:
                    r.raise_for_status()
            else:
                raise self._not_covered_error(org)
        return self._installations[org]

    def _not_covered_error(self, org):
        covered = sorted(
            inst["account"]["login"] for inst in get_installations(self.key_path)
        )
        slug = get_app_info(self.key_path)["slug"]
        return _auth_exception(
            f"The skare3 GitHub credentials cannot access '{org}'. "
            f"They currently cover: {', '.join(covered) or 'no organizations'}. "
            f"A GitHub admin of '{org}' can enable it at "
            f"https://github.com/apps/{slug}/installations/new "
            "(or set GITHUB_TOKEN to use a personal token instead)."
        )


def _auth_exception(message):
    # local import: github.py lazily imports this module, so a module-level
    # import here would be circular
    from skare3_tools.github.github import AuthException

    return AuthException(message)
