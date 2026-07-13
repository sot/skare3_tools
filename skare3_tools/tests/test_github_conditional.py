"""
Conditional-request support in the GitHub wrappers.

Behavior pinned:
- ``GithubAPI.__call__(..., etag=...)`` sends ``If-None-Match`` and returns the
  ``github.NOT_MODIFIED`` sentinel on a 304 (only when an etag was supplied).
- ``GithubAPI.get_conditional(path, state, ...)`` walks a paginated listing,
  replaying cached page bodies on 304 and recording ``{etag, body}`` per page
  in the caller-owned ``state`` dict.
- ``graphql.get_last_updated(repos)`` batches ``pushedAt``/``updatedAt`` for
  many repos into aliased queries, chunked to limit query size.
"""

import json

import responses

from skare3_tools.github import github, graphql

REPOS_URL = "https://api.github.com/orgs/sot/repos"


def test_etag_sends_if_none_match(github_api):
    api, rsps = github_api
    rsps.add(responses.GET, REPOS_URL, json=[{"name": "kadi"}], status=200)
    r = api.get("/orgs/sot/repos", etag='W/"abc"')
    assert rsps.calls[-1].request.headers["If-None-Match"] == 'W/"abc"'
    assert r.json() == [{"name": "kadi"}]


def test_304_returns_not_modified_sentinel(github_api):
    api, rsps = github_api
    rsps.add(responses.GET, REPOS_URL, status=304)
    r = api.get("/orgs/sot/repos", etag='W/"abc"')
    assert r is github.NOT_MODIFIED


def test_no_etag_leaves_request_and_response_unchanged(github_api):
    api, rsps = github_api
    rsps.add(responses.GET, REPOS_URL, json=[{"name": "kadi"}], status=200)
    r = api.get("/orgs/sot/repos")
    assert "If-None-Match" not in rsps.calls[-1].request.headers
    assert r.json() == [{"name": "kadi"}]


def test_get_conditional_populates_state_then_replays_on_304(github_api):
    api, rsps = github_api
    # First call: one page of data (with an ETag), then the empty page ending
    # the listing.
    rsps.add(
        responses.GET,
        REPOS_URL,
        json=[{"name": "kadi"}, {"name": "ska_sun"}],
        status=200,
        headers={"ETag": 'W/"page1"'},
    )
    rsps.add(responses.GET, REPOS_URL, json=[], status=200)
    state = {}
    items = api.get_conditional("/orgs/sot/repos", state)
    assert [i["name"] for i in items] == ["kadi", "ska_sun"]
    (page1_entry,) = [v for k, v in state.items() if "page=1" in k]
    assert page1_entry["etag"] == 'W/"page1"'

    # Second call: the server answers 304 and the body comes from state.
    rsps.reset()
    rsps.add(responses.GET, REPOS_URL, status=304)
    rsps.add(responses.GET, REPOS_URL, json=[], status=200)
    items = api.get_conditional("/orgs/sot/repos", state)
    assert [i["name"] for i in items] == ["kadi", "ska_sun"]
    assert rsps.calls[0].request.headers["If-None-Match"] == 'W/"page1"'


@responses.activate
def test_get_last_updated_batches_aliased_queries(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    responses.add(
        responses.POST,
        "https://api.github.com/graphql",
        json={
            "data": {
                "r0": {
                    "nameWithOwner": "sot/kadi",
                    "pushedAt": "2026-07-01T00:00:00Z",
                    "updatedAt": "2026-07-02T00:00:00Z",
                },
                "r1": None,
            }
        },
        status=200,
    )
    api = graphql.GithubAPI(token="ghp_test")
    result = graphql.get_last_updated(["sot/kadi", "sot/gone"], api=api)
    assert result == {
        "sot/kadi": {
            "pushed_at": "2026-07-01T00:00:00Z",
            "updated_at": "2026-07-02T00:00:00Z",
        },
        "sot/gone": None,
    }
    body = json.loads(responses.calls[-1].request.body)
    assert 'repository(owner: "sot", name: "kadi")' in body["query"]
    assert "pushedAt" in body["query"]


@responses.activate
def test_get_last_updated_chunks_large_lists(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    for names in (["sot/a"], ["sot/b"]):
        responses.add(
            responses.POST,
            "https://api.github.com/graphql",
            json={
                "data": {
                    "r0": {
                        "nameWithOwner": names[0],
                        "pushedAt": "2026-07-01T00:00:00Z",
                        "updatedAt": "2026-07-01T00:00:00Z",
                    }
                }
            },
            status=200,
        )
    api = graphql.GithubAPI(token="ghp_test")  # constructor sends one init query
    result = graphql.get_last_updated(["sot/a", "sot/b"], api=api, chunk_size=1)
    assert set(result) == {"sot/a", "sot/b"}
    batch_calls = [
        c
        for c in responses.calls
        if "repository(" in json.loads(c.request.body)["query"]
    ]
    assert len(batch_calls) == 2
