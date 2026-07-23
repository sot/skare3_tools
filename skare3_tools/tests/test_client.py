"""
The DataClient reader API (skare3_tools/packages/client.py).

Behavior pinned:
- source="auto": a local store wins; without one the client reads the
  published HTTP location; if that is unreachable it falls back to querying
  GitHub directly (legacy get_repositories_info).
- Explicit sources do only what they say; source="local" without a store
  raises StoreNotFoundError.
"""

import json

import pytest
import requests
import responses

from skare3_tools.config import CONFIG
from skare3_tools.packages import client, packages, store

PACKAGES = {
    "packages": [{"name": "foo", "owner": "sot"}],
    "time": "2026-07-13T00:00:00",
}
TEST_RESULTS = {"test_suites": [], "run_info": {"uid": "abc"}}


@pytest.fixture()
def populated_store(tmp_path):
    store.atomic_write_json(
        tmp_path / "manifest.json",
        {"schema_version": store.SCHEMA_VERSION, "generated": "2026-07-13T00:00:00"},
    )
    store.atomic_write_json(tmp_path / "packages.json", PACKAGES)
    store.atomic_write_json(tmp_path / "test_results.json", TEST_RESULTS)
    store.atomic_write_json(tmp_path / "repos" / "sot" / "foo.json", {"name": "foo"})
    return tmp_path


def test_auto_prefers_local_store(populated_store):
    c = client.DataClient(data_dir=populated_store)
    assert c.packages() == PACKAGES
    assert c.test_results() == TEST_RESULTS
    assert c.repository_info("sot/foo") == {"name": "foo"}


@responses.activate
def test_auto_falls_back_to_http(tmp_path):
    base = CONFIG["store_url"]
    responses.add(responses.GET, f"{base}/packages.json", json=PACKAGES, status=200)
    c = client.DataClient(data_dir=tmp_path / "empty")  # no store there
    assert c.packages() == PACKAGES


@responses.activate
def test_http_repository_info_falls_back_to_aggregate(tmp_path):
    base = CONFIG["store_url"]
    responses.add(responses.GET, f"{base}/repos/sot/foo.json", status=404)
    responses.add(responses.GET, f"{base}/packages.json", json=PACKAGES, status=200)
    c = client.DataClient(source="http")
    assert c.repository_info("sot/foo") == {"name": "foo", "owner": "sot"}


def test_auto_falls_back_to_github(tmp_path, monkeypatch):
    def no_http(*args, **kwargs):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(client.requests, "get", no_http)
    monkeypatch.setattr(
        packages, "get_repositories_info", lambda *a, **kw: dict(PACKAGES)
    )
    c = client.DataClient(data_dir=tmp_path / "empty")
    assert c.packages() == PACKAGES


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
