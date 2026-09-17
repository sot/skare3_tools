"""
The DataClient reader API (skare3_tools/packages/client.py).

Behavior pinned:
- source="auto": a local store wins; without one the client reads the
  published HTTP location; if that is unreachable it falls back to querying
  GitHub directly.
- repository_info picks the entry out of the aggregate, which holds the only
  copy of each record, so every source answers it the same way.
- Falling back is per file: a store missing one file stays authoritative for
  the others, so one absent file cannot divert every read to GitHub.
- What a client reads is remembered for its lifetime.
- Explicit sources do only what they say; source="local" without a store
  raises StoreNotFoundError.
"""

import json

import pytest
import requests
import responses

from skare3_tools.config import CONFIG
from skare3_tools.packages import client, packages, store

FOO = {
    "name": "foo",
    "owner": "sot",
    "master_version": "1.2",
    "flight": "1.1",
    "test_status": "PASS",
}
PACKAGES = {"packages": [FOO], "time": "2026-07-13T00:00:00"}
PACKAGE_LIST = [
    {"name": "foo", "package": "foo", "repository": "sot/foo", "owner": "sot"}
]
TEST_RESULTS = {"test_suites": [], "run_info": {"uid": "abc"}}


@pytest.fixture()
def populated_store(tmp_path):
    store.atomic_write_json(
        tmp_path / "manifest.json",
        {"schema_version": store.SCHEMA_VERSION, "generated": "2026-07-13T00:00:00"},
    )
    store.atomic_write_json(tmp_path / "packages.json", PACKAGES)
    store.atomic_write_json(
        tmp_path / "package_list.json", {"package_list": PACKAGE_LIST}
    )
    store.atomic_write_json(tmp_path / "test_results.json", TEST_RESULTS)
    return tmp_path


def test_auto_prefers_local_store(populated_store):
    c = client.DataClient(data_dir=populated_store)
    assert c.packages() == PACKAGES
    assert c.package_list() == PACKAGE_LIST
    assert c.test_results() == TEST_RESULTS
    assert c.generated() == "2026-07-13T00:00:00"


def test_repository_info_comes_from_the_aggregate(populated_store):
    """The only copy of a record lives in the aggregate, deployment fields included."""
    c = client.DataClient(data_dir=populated_store)
    assert c.repository_info("sot/foo") == FOO
    assert c.repository_info("sot/foo")["master_version"] == "1.2"


def test_repository_info_unknown_repository_raises(populated_store):
    c = client.DataClient(data_dir=populated_store)
    with pytest.raises(KeyError, match="sot/nope"):
        c.repository_info("sot/nope")


def test_reads_are_remembered(populated_store):
    """Picking many repositories out of the aggregate must not re-read it."""
    c = client.DataClient(data_dir=populated_store)
    c.repository_info("sot/foo")
    (populated_store / "packages.json").unlink()
    assert c.repository_info("sot/foo") == FOO


@responses.activate
def test_auto_falls_back_to_http(tmp_path):
    base = CONFIG["store_url"]
    responses.add(responses.GET, f"{base}/packages.json", json=PACKAGES, status=200)
    c = client.DataClient(data_dir=tmp_path / "empty")  # no store there
    assert c.packages() == PACKAGES
    assert c.repository_info("sot/foo") == FOO
    assert len(responses.calls) == 1


@responses.activate
def test_http_package_list(tmp_path):
    base = CONFIG["store_url"]
    responses.add(
        responses.GET,
        f"{base}/package_list.json",
        json={"package_list": PACKAGE_LIST},
        status=200,
    )
    assert client.DataClient(source="http").package_list() == PACKAGE_LIST


def test_auto_falls_back_to_github(tmp_path, monkeypatch):
    def no_http(*args, **kwargs):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(client.requests, "get", no_http)
    monkeypatch.setattr(
        packages, "_repositories_info_from_github", lambda *a, **kw: dict(PACKAGES)
    )
    c = client.DataClient(data_dir=tmp_path / "empty")
    assert c.packages() == PACKAGES


def test_github_tier_package_list(tmp_path, monkeypatch):
    monkeypatch.setattr(
        packages, "_package_list_from_github", lambda: list(PACKAGE_LIST)
    )
    c = client.DataClient(source="github")
    assert c.package_list() == PACKAGE_LIST


def test_explicit_local_without_store_raises(tmp_path):
    with pytest.raises(store.StoreNotFoundError):
        client.DataClient(source="local", data_dir=tmp_path / "empty").packages()


@responses.activate
def test_explicit_url_overrides_config(tmp_path):
    url = "https://example.org/data"
    responses.add(responses.GET, f"{url}/packages.json", json=PACKAGES, status=200)
    c = client.DataClient(source="http", url=url)
    assert c.packages() == PACKAGES
    assert json.loads(responses.calls[-1].response.text) == PACKAGES


@responses.activate
def test_a_missing_file_does_not_divert_the_other_reads(tmp_path):
    """
    The case a store written by an older layout presents.

    package_list.json is absent from the store and unpublished, while
    packages.json is right there. Reading the first must not condemn the
    second to a GitHub query -- that was ~200 repositories of needless work.
    """
    store.atomic_write_json(
        tmp_path / "manifest.json",
        {"schema_version": store.SCHEMA_VERSION - 1},  # an older layout
    )
    store.atomic_write_json(tmp_path / "packages.json", PACKAGES)
    base = CONFIG["store_url"]
    # the published location does not have it either: an error page, status 200
    responses.add(
        responses.GET, f"{base}/package_list.json", body="<html>404</html>", status=200
    )
    responses.add(
        responses.GET,
        f"{base}/packages.json",
        json={"packages": []},
        status=200,
    )

    c = client.DataClient(data_dir=tmp_path)
    from_github = []
    original = packages._package_list_from_github
    packages._package_list_from_github = lambda: from_github.append(1) or PACKAGE_LIST
    try:
        assert c.package_list() == PACKAGE_LIST  # only this one falls through
    finally:
        packages._package_list_from_github = original
    assert from_github == [1]

    # ... and the aggregate still comes from the store, untouched by that
    assert c.packages() == PACKAGES
    assert c.repository_info("sot/foo") == FOO
    assert [call.request.url for call in responses.calls] == [
        f"{base}/package_list.json"
    ]


def test_sources_chain_per_configured_source(tmp_path, populated_store):
    assert client.DataClient(data_dir=populated_store).sources() == (
        "local",
        "http",
        "github",
    )
    assert client.DataClient(data_dir=tmp_path / "empty").sources() == (
        "http",
        "github",
    )
    assert client.DataClient(source="local").sources() == ("local",)
    assert client.DataClient(source="github").sources() == ("github",)


def test_test_results_never_falls_back_to_github(tmp_path, monkeypatch):
    """There is no Github equivalent, so the http error is the useful one."""

    def no_http(*args, **kwargs):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(client.requests, "get", no_http)
    c = client.DataClient(data_dir=tmp_path / "empty")
    with pytest.raises(requests.ConnectionError):
        c.test_results()
