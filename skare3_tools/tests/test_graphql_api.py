"""
Characterize the GraphQL wrapper GithubAPI (skare3_tools/github/graphql.py).

Behavior pinned:
- Every query goes through a single POST chokepoint at graphql.py:441, sending
  ``{"query": ...}`` with an ``Authorization: token ...`` header.
- ``__call__(query)`` returns the parsed JSON body.

- The constructor never accesses the network and never raises: it only resolves
  credentials, swallowing the missing-token AuthException. It is ``init()``
  (which checks the credentials) and the first call that raise.
"""

import json

import pytest
import responses

from skare3_tools.github import graphql


@responses.activate
def test_graphql_post_body_and_auth(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    responses.add(
        responses.POST,
        "https://api.github.com/graphql",
        json={"data": {"viewer": {"login": "tester"}}},
        status=200,
    )
    api = graphql.GithubAPI(token="ghp_test")
    result = api("query { viewer { login } }")
    body = json.loads(responses.calls[-1].request.body)
    assert body["query"].startswith("query")
    assert "ghp_test" in responses.calls[-1].request.headers["Authorization"]
    assert result["data"]["viewer"]["login"] == "tester"


def test_graphql_no_token_raises(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_API_TOKEN", raising=False)
    # The constructor defers the error when no token is available...
    api = graphql.GithubAPI(token=None)
    assert not api.initialized
    # ...but init() surfaces it.
    with pytest.raises(graphql.AuthException):
        api.init(token=None)
    # ...and so does using it.
    with pytest.raises(graphql.AuthException):
        api("{viewer {login}}")


@responses.activate
def test_creating_the_api_makes_no_requests(monkeypatch):
    # no stub is registered: any request would raise ConnectionError. Creating
    # the API must work offline (and with a stale token), so that importing
    # skare3_tools does not depend on the network.
    monkeypatch.setenv("GITHUB_API_TOKEN", "expired")
    api = graphql.GithubAPI()
    assert api.initialized
    assert not responses.calls
