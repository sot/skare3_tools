"""
Characterize the REST wrapper GithubAPI (skare3_tools/github/github.py).

Behavior pinned:
- Token resolution precedence: GITHUB_API_TOKEN over GITHUB_TOKEN (github.py:199-207).
- A 401 during init raises AuthException (github.py:218-225).
- ``:owner`` / ``:repo`` path templating and full-URL passthrough in __call__.
- ``check=True`` raises RestException carrying the HTTP status (github.py:242-245).

Adjust-to-reality note: the 401 branch does ``r.json()["message"]`` before raising,
so the stubbed 401 response must include a ``message`` key -- otherwise a KeyError
would surface instead of AuthException.
"""

import pytest
import responses

from skare3_tools.github import github


@responses.activate
def test_token_resolution_precedence(monkeypatch):
    responses.add(responses.GET, "https://api.github.com/", json={}, status=200)
    responses.add(
        responses.GET, "https://api.github.com/user", json={"login": "t"}, status=200
    )
    monkeypatch.setenv("GITHUB_API_TOKEN", "aaa")
    monkeypatch.setenv("GITHUB_TOKEN", "bbb")
    api = github.GithubAPI()
    assert api.headers["Authorization"] == "token aaa"   # GITHUB_API_TOKEN wins

    monkeypatch.delenv("GITHUB_API_TOKEN")
    api = github.GithubAPI()
    assert api.headers["Authorization"] == "token bbb"


@responses.activate
def test_bad_token_raises_auth_exception():
    responses.add(
        responses.GET,
        "https://api.github.com/",
        json={"message": "Bad credentials"},
        status=401,
    )
    with pytest.raises(github.AuthException):
        github.GithubAPI(token="bad")


def test_url_building(github_api):
    api, rsps = github_api
    rsps.add(
        responses.GET,
        "https://api.github.com/repos/sot/skare3/releases",
        json=[{"tag_name": "2026.8"}],
        status=200,
    )
    # :param substitution
    r = api.get("/repos/:owner/:repo/releases", owner="sot", repo="skare3")
    assert r.json()[0]["tag_name"] == "2026.8"
    # full-URL passthrough hits the same stub
    r = api.get("https://api.github.com/repos/sot/skare3/releases")
    assert r.ok


def test_check_raises_rest_exception(github_api):
    api, rsps = github_api
    rsps.add(
        responses.GET,
        "https://api.github.com/repos/sot/nope",
        json={"message": "Not Found"},
        status=404,
    )
    with pytest.raises(github.RestException, match="404"):
        api.get("/repos/:owner/:repo", owner="sot", repo="nope", check=True)
