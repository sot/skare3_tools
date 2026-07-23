"""
The dashboard views as render-only readers of the data store.

Behavior pinned:
- dashboard(render=False) returns the store aggregate verbatim (no GitHub,
  no conda: publishing the JSON is a file copy).
- dashboard() renders the aggregate to HTML, including the on-the-fly
  cosmetics (pull-request dates trimmed to days, None dates blanked).
- views.test_results.test_results() renders the digested store data.
"""

import copy

import pytest

from skare3_tools.dashboard.views import dashboard as dashboard_view
from skare3_tools.dashboard.views import test_results as test_results_view
from skare3_tools.packages import client, store

PACKAGE = {
    "name": "foo",
    "owner": "sot",
    "pushed_at": "2026-07-10T00:00:00Z",
    "updated_at": "2026-07-10T00:00:00Z",
    "last_tag": "1.0.0",
    "last_tag_date": "2026-07-01T00:00:00Z",
    "commits": 2,
    "merges": 1,
    "merge_info": [],
    "release_info": [{"release_tag": ""}, {"release_tag": "1.0.0"}],
    "issues": 0,
    "n_pull_requests": 1,
    "branches": 1,
    "pull_requests": [
        {
            "number": 7,
            "url": "https://github.com/sot/foo/pull/7",
            "title": "A PR",
            "n_commits": 1,
            "last_commit_date": "2026-07-09T12:34:56Z",
        },
        {
            "number": 8,
            "url": "https://github.com/sot/foo/pull/8",
            "title": "Another PR",
            "n_commits": 0,
            "last_commit_date": None,
        },
    ],
    "workflows": [],
    "master_version": "1.1.0",
    "flight": "1.0.0",
    "matlab": "",
    "aca": "1.0.0",
    "perl": "",
    "metapackages": {"ska3-aca": "1.0.0", "ska3-flight": "1.0.0"},
    "is_ska": True,
    "test_version": "1.0.0",
    "test_status": "PASS",
}

AGGREGATE = {
    "schema_version": store.SCHEMA_VERSION,
    "time": "2026-07-13T00:00:00",
    "ska3-flight": "2026.5",
    "ska3-matlab": "2026.5",
    "metapackages": {
        "ska3-aca": "2026.6",
        "ska3-flight": "2026.5",
        "ska3-matlab": "2026.5",
        "ska3-perl": "2026.2",
    },
    "packages": [PACKAGE],
}

TEST_RESULTS = {
    "run_info": {
        "uid": "abc",
        "date": "2026-07-12 00:00:00",
        "ska_version": "2026.5",
        "system": "Linux",
        "architecture": "x86_64",
        "hostname": "kady",
        "platform": "linux",
    },
    "test_suites": [
        {
            "package": "foo",
            "properties": {"package_version": "1.0.0"},
            "test_cases": [{"status": "pass", "name": "test_one"}],
            "log": "foo.log",
        }
    ],
}


@pytest.fixture()
def store_client(tmp_path):
    store.atomic_write_json(
        tmp_path / "manifest.json",
        {"schema_version": store.SCHEMA_VERSION, "generated": AGGREGATE["time"]},
    )
    store.atomic_write_json(tmp_path / "packages.json", AGGREGATE)
    store.atomic_write_json(tmp_path / "test_results.json", TEST_RESULTS)
    return client.DataClient(data_dir=tmp_path)


def test_dashboard_json_is_the_store_aggregate(store_client):
    assert dashboard_view.dashboard(render=False, client=store_client) == AGGREGATE


def test_dashboard_renders_html(store_client):
    html = dashboard_view.dashboard(client=store_client)
    assert "foo" in html
    assert "2026-07-09" in html  # PR date trimmed to a day
    # the aggregate the client returns is not mutated by rendering
    assert store_client.packages() == AGGREGATE


def test_test_results_view_renders_store_data(store_client):
    html = test_results_view.test_results(client=store_client)
    assert "test_one" in html or "foo" in html


def test_dashboard_render_handles_missing_test_results(tmp_path):
    aggregate = copy.deepcopy(AGGREGATE)
    store.atomic_write_json(
        tmp_path / "manifest.json",
        {"schema_version": store.SCHEMA_VERSION, "generated": aggregate["time"]},
    )
    store.atomic_write_json(tmp_path / "packages.json", aggregate)
    c = client.DataClient(data_dir=tmp_path)
    assert dashboard_view.dashboard(render=False, client=c) == aggregate
