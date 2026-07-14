"""
The skare3-refresh producer (skare3_tools/packages/refresh.py).

Behavior pinned:
- A full refresh writes a schema-2 store: manifest.json, packages.json,
  test_results.json, repos/{owner}/{name}.json and meta/state.json, with all
  the fields the dashboard consumes plus the metapackage model
  (aca/flight/matlab/perl membership + pins, is_ska).
- Deprecated repositories are not fetched and not in the aggregate; they are
  listed in manifest["excluded"].
- A second run with unchanged pushedAt/updatedAt fetches no repository detail
  (change detection via the batched last-updated query).
- A missing metapackage aborts the run before anything is written.
- A per-repository fetch failure keeps the previous good file in the
  aggregate and is reported in the summary.
"""

import pytest

from skare3_tools import test_results
from skare3_tools.github import graphql
from skare3_tools.packages import packages, refresh, store

V4_INFO = {
    "last_tag": "1.0.0",
    "last_tag_date": "2026-07-01T00:00:00Z",
    "commits": 2,
    "merges": 1,
    "merge_info": [],
    "release_info": [{"release_tag": ""}, {"release_tag": "1.0.0"}],
    "issues": 0,
    "n_pull_requests": 0,
    "branches": 1,
    "pull_requests": [],
    "workflows": [],
}

LAST_UPDATED = {
    "sot/foo": {
        "pushed_at": "2026-07-10T00:00:00Z",
        "updated_at": "2026-07-10T00:00:00Z",
    },
    "sot/bar": {
        "pushed_at": "2026-07-09T00:00:00Z",
        "updated_at": "2026-07-09T00:00:00Z",
    },
}

CONDA_MAIN = {
    "ska3-aca": [{"version": "2026.6", "depends": {"foo": "1.0.0"}}],
    "ska3-flight": [
        {"version": "2026.5", "depends": {"foo": "1.0.0", "ska_helpers": ""}}
    ],
    "ska3-matlab": [{"version": "2026.5", "depends": {}}],
    "ska3-perl": [{"version": "2026.2", "depends": {"perl-ska-classic": "4.1"}}],
}

CONDA_MASTERS = {
    "foo": [{"version": "1.1.0", "depends": {}}],
}

TEST_RUN = {
    "run_info": {"uid": "abc", "date": "2026-07-12 00:00:00"},
    "test_suites": [
        {
            "package": "foo",
            "properties": {"package_version": "1.0.0"},
            "test_cases": [{"status": "pass"}, {"status": "skipped"}],
        }
    ],
}


class FakeOrganization:
    repos = {
        "sot": ["foo", "bar"],
        "acisops": ["dpa_check"],
    }

    def __init__(self, name):
        self.name = name

    def repositories(self):
        return [
            {"full_name": f"{self.name}/{name}", "owner": {"login": self.name}}
            for name in self.repos.get(self.name, [])
        ]


@pytest.fixture()
def fake_github(monkeypatch, fake_skare3_repo):
    """Stub every external source the producer touches."""
    calls = {"v4": []}

    def fake_v4(owner_repo, **kwargs):
        calls["v4"].append(owner_repo)
        owner, name = owner_repo.split("/")
        return dict(
            V4_INFO,
            owner=owner,
            name=name,
            **LAST_UPDATED.get(owner_repo, {"pushed_at": "", "updated_at": ""}),
        )

    def fake_conda(pattern, conda_channel=None):
        assert pattern == "*"
        return {"main": CONDA_MAIN, "masters": CONDA_MASTERS}[conda_channel]

    monkeypatch.setattr(packages.github, "Organization", FakeOrganization)
    monkeypatch.setattr(packages, "_get_repository_info_v4", fake_v4)
    monkeypatch.setattr(packages, "get_conda_pkg_info", fake_conda)
    monkeypatch.setattr(
        graphql,
        "get_last_updated",
        lambda repos, **kw: dict.fromkeys(repos) | LAST_UPDATED,
    )
    monkeypatch.setattr(test_results, "get_latest", lambda **kw: dict(TEST_RUN))
    return calls


@pytest.fixture()
def clean_store(data_dir):
    for name in ("manifest.json", "packages.json", "test_results.json"):
        if (data_dir / name).exists():
            (data_dir / name).unlink()
    for sub in ("repos", "meta"):
        import shutil

        if (data_dir / sub).exists():
            shutil.rmtree(data_dir / sub)
    # get_package_list is json_cache'd with a 1-day expiry: remove the entry
    # so each test sees its own FakeOrganization universe.
    packages.get_package_list.clear_cache()
    return data_dir


def test_full_refresh_writes_schema2_store(fake_github, clean_store):
    summary = refresh.refresh()
    assert summary["failures"] == {}

    reader = store.StoreReader(clean_store)
    manifest = reader.manifest()
    assert manifest["schema_version"] == store.SCHEMA_VERSION
    assert "acisops/dpa_check" in manifest["excluded"]

    info = reader.packages()
    # legacy top-level fields, consumed by the React dashboard
    assert info["ska3-flight"] == "2026.5"
    assert info["ska3-matlab"] == "2026.5"
    assert info["time"]
    # new metapackage model
    assert info["metapackages"]["ska3-perl"] == "2026.2"

    by_name = {p["name"]: p for p in info["packages"]}
    assert "dpa_check" not in {n.split("/")[-1] for n in by_name}
    foo = by_name["foo"]
    # legacy per-package fields
    assert foo["flight"] == "1.0.0"
    assert foo["matlab"] == ""
    assert foo["master_version"] == "1.1.0"
    assert foo["test_status"] == "PASS"
    assert foo["test_version"] == "1.0.0"
    assert foo["release_info"][1]["release_tag"] == "1.0.0"
    # new per-package fields
    assert foo["aca"] == "1.0.0"
    assert foo["perl"] == ""
    assert foo["metapackages"] == {"ska3-aca": "1.0.0", "ska3-flight": "1.0.0"}
    assert foo["is_ska"] is True
    bar = by_name["bar"]  # org repo with no pkg_def
    assert bar["is_ska"] is False
    assert bar["flight"] == ""

    assert reader.repository_info("sot/foo")["name"] == "foo"
    assert reader.test_results()["test_suites"][0]["status"] == "pass"


def test_second_run_fetches_nothing_when_unchanged(fake_github, clean_store):
    refresh.refresh()
    fake_github["v4"].clear()
    refresh.refresh()
    assert fake_github["v4"] == []


def test_changed_repo_is_refetched(fake_github, clean_store, monkeypatch):
    refresh.refresh()
    fake_github["v4"].clear()
    bumped = dict(LAST_UPDATED)
    bumped["sot/foo"] = dict(LAST_UPDATED["sot/foo"], pushed_at="2026-07-13T00:00:00Z")
    monkeypatch.setattr(
        graphql, "get_last_updated", lambda repos, **kw: dict.fromkeys(repos) | bumped
    )
    refresh.refresh()
    assert fake_github["v4"] == ["sot/foo"]


def test_missing_metapackage_aborts_before_writing(
    fake_github, clean_store, monkeypatch
):
    incomplete = {k: v for k, v in CONDA_MAIN.items() if k != "ska3-perl"}
    monkeypatch.setattr(
        packages,
        "get_conda_pkg_info",
        lambda pattern, conda_channel=None: {
            "main": incomplete,
            "masters": CONDA_MASTERS,
        }[conda_channel],
    )
    with pytest.raises(refresh.RefreshError, match="ska3-perl"):
        refresh.refresh()
    assert not (clean_store / "packages.json").exists()


def test_repo_fetch_failure_keeps_previous_data(fake_github, clean_store, monkeypatch):
    refresh.refresh()

    def failing_v4(owner_repo, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(packages, "_get_repository_info_v4", failing_v4)
    summary = refresh.refresh(full=True)
    assert set(summary["failures"]) == {"sot/foo", "sot/bar"}
    # the aggregate still carries the previously-fetched data
    info = store.StoreReader(clean_store).packages()
    assert {p["name"] for p in info["packages"]} == {"foo", "bar"}


def test_no_test_results_yet(fake_github, clean_store, monkeypatch):
    monkeypatch.setattr(
        test_results,
        "get_latest",
        lambda **kw: (_ for _ in ()).throw(FileNotFoundError()),
    )
    refresh.refresh()
    info = store.StoreReader(clean_store).packages()
    assert all(p["test_status"] == "" for p in info["packages"])
