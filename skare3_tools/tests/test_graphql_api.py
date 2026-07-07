"""
Characterize the GraphQL wrapper GithubAPI (skare3_tools/github/graphql.py).

Behavior pinned:
- Every query goes through a single POST chokepoint at graphql.py:441, sending
  ``{"query": ...}`` with an ``Authorization: token ...`` header.
- ``__call__(query)`` returns the parsed JSON body.

Adjust-to-reality note: the constructor *defers* the missing-token error -- with
``token=None`` it swallows AuthException (graphql.py:367-371) so an uninitialized
API can be created and used later. It is ``init()`` that raises AuthException when
no token is available (graphql.py:398-404). The test pins both halves of that
contract rather than asserting the constructor raises.
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
