"""
The skare3-refresh producer (skare3_tools/packages/refresh.py).

Behavior pinned:
- A full refresh writes the store: manifest.json, packages.json,
  package_list.json, test_results.json and meta/state.json, with all the
  fields the dashboard consumes plus the metapackage model
  (aca/flight/matlab/perl membership + pins, is_ska). packages.json holds the
  only copy of each repository record -- there is no per-repository tree.
- package_list.json is the *unfiltered* universe: consumers resolving an old
  metapackage version need packages of excluded repositories too.
- If the recipes cannot be fetched, the stored package list stands in for them
  and the run says so; with neither, the run aborts.
- The aggregate records the arguments its records were produced with, so
  get_repository_info can tell what the store can answer.
- Reuse turns on the record shape (record_version / record_options), not the
  store layout: an aggregate from an older schema_version is still a valid
  source of records and must not trigger a full refetch.
- Every repository is re-enriched every run, including the ones whose detail
  was not refetched: the deployment-stage fields move with the channels and
  the test runs, not with repository pushes.
- Repositories listed in repository_status.json ("deprecated" or "ignored")
  are not fetched and not in the aggregate; they are listed in
  manifest["excluded"]. The file is seeded once when missing, never
  overwritten, and an unknown status aborts the run.
- A second run with unchanged pushedAt/updatedAt fetches no repository detail
  (change detection via the batched last-updated query).
- A missing metapackage aborts the run before anything is written.
- A per-repository fetch failure keeps the previous good record in the
  aggregate, is reported in the summary, and does not advance the change
  detection state, so the next run retries.
- With no readable test run, the tested versions already in the store are kept
  rather than blanked (also for repositories refetched in that run), and the
  run is reported as a failure.
- A test that errored makes the package FAIL.
"""

import json

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
    import shutil

    names = (
        "manifest.json",
        "packages.json",
        "package_list.json",
        "test_results.json",
        "repository_status.json",
    )
    for name in names:
        if (data_dir / name).exists():
            (data_dir / name).unlink()
    if (data_dir / "meta").exists():
        shutil.rmtree(data_dir / "meta")
    return data_dir


def test_full_refresh_writes_the_store(fake_github, clean_store):
    summary = refresh.refresh()
    assert summary["failures"] == {}

    reader = store.StoreReader(clean_store)
    manifest = reader.manifest()
    assert manifest["schema_version"] == store.SCHEMA_VERSION
    assert "acisops/dpa_check" in manifest["excluded"]

    # the status file was seeded and echoed into the manifest
    seeded = store.repository_status(clean_store)
    assert seeded == refresh.INITIAL_REPOSITORY_STATUS
    assert seeded["sot/test-actions"] == "ignored"
    assert manifest["repository_status"] == seeded

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

    # a single-repository read comes out of the aggregate: its only copy
    assert reader.repository_info("sot/foo") == foo
    assert not (clean_store / "repos").exists()
    assert reader.test_results()["test_suites"][0]["status"] == "pass"

    # the arguments the records were produced with, for get_repository_info
    assert info["record_options"] == packages.record_options()
    assert info["record_options"]["since"] == 7


def test_package_list_is_stored_unfiltered(fake_github, clean_store):
    """Excluded repositories stay in the list: old metapackages still name them."""
    refresh.refresh()
    package_list = store.StoreReader(clean_store).package_list()
    repositories = {p["repository"] for p in package_list}
    assert "acisops/dpa_check" in repositories  # excluded from the aggregate
    aggregated = {
        f"{p['owner']}/{p['name']}"
        for p in store.StoreReader(clean_store).packages()["packages"]
    }
    assert "acisops/dpa_check" not in aggregated


def test_status_file_is_input_not_overwritten(fake_github, clean_store):
    operator_map = {"sot/bar": "ignored"}
    (clean_store / "repository_status.json").write_text(json.dumps(operator_map))
    refresh.refresh()

    reader = store.StoreReader(clean_store)
    names = {p["name"] for p in reader.packages()["packages"]}
    # the operator's map wins: bar is out, and the seed was not applied
    # (dpa_check would be excluded by it)
    assert names == {"foo", "dpa_check"}
    assert reader.manifest()["excluded"] == ["sot/bar"]
    assert store.repository_status(clean_store) == operator_map


def test_unknown_status_fails_loudly(fake_github, clean_store):
    (clean_store / "repository_status.json").write_text(
        json.dumps({"sot/foo": "deprectaed"})
    )
    with pytest.raises(refresh.RefreshError, match="deprectaed"):
        refresh.refresh()
    assert not (clean_store / "packages.json").exists()


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


def test_repo_fetch_failure_is_retried_next_run(fake_github, clean_store, monkeypatch):
    """A failed fetch must not advance the change-detection state."""
    refresh.refresh()
    bumped = dict(LAST_UPDATED)
    bumped["sot/foo"] = dict(LAST_UPDATED["sot/foo"], pushed_at="2026-07-13T00:00:00Z")
    monkeypatch.setattr(
        graphql, "get_last_updated", lambda repos, **kw: dict.fromkeys(repos) | bumped
    )

    working_v4 = packages._get_repository_info_v4
    monkeypatch.setattr(
        packages,
        "_get_repository_info_v4",
        lambda owner_repo, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert set(refresh.refresh()["failures"]) == {"sot/foo"}

    monkeypatch.setattr(packages, "_get_repository_info_v4", working_v4)
    fake_github["v4"].clear()
    assert refresh.refresh()["written"] == ["sot/foo"]
    assert fake_github["v4"] == ["sot/foo"]


def test_skipped_repo_still_gets_new_deployment_versions(
    fake_github, clean_store, monkeypatch
):
    """
    The five deployment-stage fields are refresh-time state, not repository
    properties: a repository with no pushes still moves through the pipeline.
    """
    refresh.refresh()
    assert (
        store.StoreReader(clean_store).repository_info("sot/foo")["master_version"]
        == "1.1.0"
    )

    monkeypatch.setattr(
        packages,
        "get_conda_pkg_info",
        lambda pattern, conda_channel=None: {
            "main": CONDA_MAIN,
            "masters": {"foo": [{"version": "1.2.0", "depends": {}}]},
        }[conda_channel],
    )
    monkeypatch.setattr(
        test_results,
        "get_latest",
        lambda **kw: dict(
            TEST_RUN,
            test_suites=[
                dict(
                    TEST_RUN["test_suites"][0],
                    properties={"package_version": "1.1.0"},
                    test_cases=[{"status": "fail"}],
                )
            ],
        ),
    )
    fake_github["v4"].clear()
    summary = refresh.refresh()

    assert "sot/foo" in summary["skipped"]  # no repository detail refetched
    assert fake_github["v4"] == []
    foo = store.StoreReader(clean_store).repository_info("sot/foo")
    assert foo["master_version"] == "1.2.0"
    assert foo["test_version"] == "1.1.0"
    assert foo["test_status"] == "FAIL"


def test_no_test_results_yet(fake_github, clean_store, monkeypatch):
    monkeypatch.setattr(
        test_results,
        "get_latest",
        lambda **kw: (_ for _ in ()).throw(FileNotFoundError()),
    )
    refresh.refresh()
    info = store.StoreReader(clean_store).packages()
    assert all(p["test_status"] == "" for p in info["packages"])


def test_changed_record_options_invalidate_reuse(fake_github, clean_store, monkeypatch):
    """Reused and refetched records must never have different shapes."""
    refresh.refresh()
    aggregate = json.loads((clean_store / "packages.json").read_text())
    aggregate["record_options"] = dict(aggregate["record_options"], since=30)
    (clean_store / "packages.json").write_text(json.dumps(aggregate))

    fake_github["v4"].clear()
    refresh.refresh()
    assert sorted(fake_github["v4"]) == ["sot/bar", "sot/foo"]


def _no_test_results(monkeypatch):
    monkeypatch.setattr(
        test_results,
        "get_latest",
        lambda **kw: (_ for _ in ()).throw(FileNotFoundError()),
    )


def test_unreadable_test_run_keeps_the_stored_versions(
    fake_github, clean_store, monkeypatch
):
    """Blanking every test status is indistinguishable from "nothing passed"."""
    refresh.refresh()
    before = store.StoreReader(clean_store).repository_info("sot/foo")
    assert before["test_status"] == "PASS"

    _no_test_results(monkeypatch)
    summary = refresh.refresh()

    after = store.StoreReader(clean_store).repository_info("sot/foo")
    assert after["test_status"] == "PASS"
    assert after["test_version"] == before["test_version"]
    # and the run says so, so the scheduler notices
    assert any("test results" in key for key in summary["failures"])


def test_unreadable_test_run_on_a_first_run_leaves_the_fields_empty(
    fake_github, clean_store, monkeypatch
):
    """With nothing stored to keep, the fields still have to be present."""
    _no_test_results(monkeypatch)
    refresh.refresh()
    info = store.StoreReader(clean_store).packages()
    assert all(p["test_status"] == "" for p in info["packages"])
    assert all(p["test_version"] == "" for p in info["packages"])


def test_older_schema_aggregate_is_still_reused(fake_github, clean_store):
    """
    Moving the store's files around does not invalidate the records in it.

    A schema bump that leaves the record shape alone must not cost a refetch of
    every repository -- that is thousands of GraphQL queries for nothing.
    """
    refresh.refresh()
    aggregate = json.loads((clean_store / "packages.json").read_text())
    # exactly what a store written before this schema looks like: an older
    # layout version, and none of the record-shape fields
    aggregate["schema_version"] = store.SCHEMA_VERSION - 1
    del aggregate["record_version"]
    del aggregate["record_options"]
    (clean_store / "packages.json").write_text(json.dumps(aggregate))
    (clean_store / "manifest.json").write_text(
        json.dumps({"schema_version": store.SCHEMA_VERSION - 1})
    )

    fake_github["v4"].clear()
    summary = refresh.refresh()
    assert fake_github["v4"] == []
    assert sorted(summary["skipped"]) == ["sot/bar", "sot/foo"]
    # and the rewritten store is current again
    info = store.StoreReader(clean_store).packages()
    assert info["record_version"] == store.RECORD_VERSION
    assert info["schema_version"] == store.SCHEMA_VERSION


def test_changed_record_version_invalidates_reuse(
    fake_github, clean_store, monkeypatch
):
    """A change in the record's own fields does force a refetch."""
    refresh.refresh()
    aggregate = json.loads((clean_store / "packages.json").read_text())
    aggregate["record_version"] = store.RECORD_VERSION + 1
    (clean_store / "packages.json").write_text(json.dumps(aggregate))

    fake_github["v4"].clear()
    refresh.refresh()
    assert sorted(fake_github["v4"]) == ["sot/bar", "sot/foo"]


def _recipes_unavailable(monkeypatch):
    def boom():
        raise packages.RecipesUnavailable("cannot fetch the sot/skare3 recipes")

    monkeypatch.setattr(packages, "_package_list_from_github", boom)


def test_unavailable_recipes_fall_back_to_the_stored_list(
    fake_github, clean_store, monkeypatch
):
    """The store holds the parsed product of an earlier fetch: use it, loudly."""
    refresh.refresh()
    before = json.loads((clean_store / "package_list.json").read_text())

    _recipes_unavailable(monkeypatch)
    summary = refresh.refresh()

    assert "package list" in summary["failures"]
    names = {p["name"] for p in store.StoreReader(clean_store).packages()["packages"]}
    assert names == {"foo", "bar"}
    # the stored list is not rewritten, so its timestamp keeps telling the truth
    assert json.loads((clean_store / "package_list.json").read_text()) == before


def test_unavailable_recipes_with_no_stored_list_aborts(
    fake_github, clean_store, monkeypatch
):
    _recipes_unavailable(monkeypatch)
    with pytest.raises(refresh.RefreshError, match="no package list"):
        refresh.refresh()
    assert not (clean_store / "packages.json").exists()


def test_errored_tests_count_as_a_failure(fake_github, clean_store, monkeypatch):
    """A test that errored did not pass."""
    suite = dict(
        TEST_RUN["test_suites"][0], test_cases=[{"status": "pass"}, {"status": "error"}]
    )
    run = dict(TEST_RUN, test_suites=[suite])
    monkeypatch.setattr(test_results, "get_latest", lambda **kw: run)
    refresh.refresh()
    foo = store.StoreReader(clean_store).repository_info("sot/foo")
    assert foo["test_status"] == "FAIL"


def test_unreadable_test_run_keeps_the_stored_versions_of_refetched_repos(
    fake_github, clean_store, monkeypatch
):
    """A refetched record has no test fields: they come from the stored one."""
    refresh.refresh()
    _no_test_results(monkeypatch)
    fake_github["v4"].clear()
    refresh.refresh(full=True)
    assert sorted(fake_github["v4"]) == ["sot/bar", "sot/foo"]
    foo = store.StoreReader(clean_store).repository_info("sot/foo")
    assert foo["test_status"] == "PASS"
    assert foo["test_version"] == "1.0.0"
