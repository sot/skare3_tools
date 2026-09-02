"""
packages.get_package_list, and the public read API's choice of data source.

The audited contract: each entry is a dict with keys name / package / repository /
owner; a recipe with no ``about.home`` yields repository/owner None; organization
repositories with no local pkg_def are appended; the result is sorted.

Adjust-to-reality notes (pinned against packages.py while writing):
- ``repository`` is the *full* ``owner/repo`` string, not the bare repo name.
  ``_conda_package_list`` sets ``pkg_info["repository"] = "{org}/{repo}"``
  (packages.py:277), so foo -> "sot/foo".
- The org protocol: ``get_package_list`` calls ``org.repositories()`` and reads
  ``r["full_name"]`` and ``r["owner"]["login"]``, so the fake must return dicts
  keyed by ``full_name`` (not ``name``).

The public functions (get_repository_info, get_repositories_info,
get_package_list) read the data store; they query Github only when asked for
something the store does not hold -- a different ``since`` -- or with
``update=True``. Both directions are pinned below.
"""

import pytest

from skare3_tools import packages
from skare3_tools.packages import store


class FakeOrganization:
    """Stands in for github.Organization in get_package_list.

    get_package_list does ``[r for org in orgs for r in org.repositories()]`` and
    then reads ``r["full_name"]`` / ``r["owner"]["login"]``.
    """

    def __init__(self, name, **kwargs):
        self.name = name

    def repositories(self):
        return [{"full_name": "sot/bar", "owner": {"login": "sot"}}]


def test_get_package_list_parses_pkg_defs(monkeypatch, fake_skare3_repo):
    monkeypatch.setattr(packages.github, "Organization", FakeOrganization)
    result = packages.get_package_list(update=True)
    by_name = {p["name"]: p for p in result if p["name"]}
    foo = by_name["foo"]
    assert foo["repository"] == "sot/foo"  # full owner/repo, from about.home
    assert foo["owner"] == "sot"
    assert foo["package"] == "foo"
    assert by_name["nohome"]["repository"] is None  # no about.home -> no repo
    assert by_name["nohome"]["owner"] is None
    # extra org repo appended even though it has no pkg_def
    assert any(p["repository"] == "sot/bar" and p["package"] is None for p in result)
    # sorted output (matches production sort key: repository-or-"" then name)
    keys = [((p["repository"] or ""), p["name"]) for p in result]
    assert keys == sorted(keys)


def test_get_package_list_skips_bad_recipe(monkeypatch, fake_skare3_repo):
    monkeypatch.setattr(packages.github, "Organization", FakeOrganization)
    result = packages.get_package_list(update=True)  # badpkg present in fixtures
    assert all(p["name"] != "badpkg" for p in result)  # skipped, not raised


def test_get_all_nodes_forwards_org(monkeypatch):
    from skare3_tools import packages

    orgs_seen = []

    def fake_api(query, org=None, **kwargs):
        orgs_seen.append(org)
        return {
            "data": {
                "repository": {
                    "refs": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }

    monkeypatch.setattr(packages.github, "GITHUB_API_V4", fake_api)
    packages.get_all_nodes(
        owner="acisops", name="foo", path="data/repository/refs", query="{}"
    )
    assert orgs_seen == ["acisops"]


def test_public_api_reexported():
    # Everything external code imports from skare3_tools.packages must stay
    # importable after the module became a subpackage.
    for name in [
        "get_package_list",
        "get_repository_info",
        "get_repositories_info",
        "get_conda_pkg_info",
        "get_conda_pkg_dependencies",
        "record_options",
        "RecipesUnavailable",
        "NetworkException",
        "get_parser",
        "main",
        "_get_release_commit",  # used by github/scripts/release_merge_info.py
    ]:
        assert getattr(packages, name) is not None
    assert packages.github is not None  # patched by tests via packages.github


def test_channel_probe_retries_transient_timeouts(monkeypatch):
    from skare3_tools.packages import packages as packages_module

    calls = []

    def flaky_get(url, timeout=None):
        calls.append(url)
        if len(calls) < 3:
            raise packages_module.requests.ReadTimeout

    monkeypatch.setattr(packages_module.requests, "get", flaky_get)
    monkeypatch.setattr(packages_module.time, "sleep", lambda seconds: None)
    assert packages_module._channel_is_reachable("https://u:p@example.org/channel")
    assert len(calls) == 3


def test_unreachable_channel_reported_without_credentials(monkeypatch):
    from skare3_tools.packages import packages as packages_module

    def timing_out_get(url, timeout=None):
        raise packages_module.requests.ReadTimeout

    monkeypatch.setattr(packages_module.requests, "get", timing_out_get)
    monkeypatch.setattr(packages_module.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("CONDA_PASSWORD", "hunter2")
    with pytest.raises(packages_module.NetworkException) as exc_info:
        packages_module.get_conda_pkg_info(
            "foo", conda_channel="https://ska:{CONDA_PASSWORD}@example.org/channel"
        )
    assert "example.org" in str(exc_info.value)
    assert "hunter2" not in str(exc_info.value)


class FakeClient:
    """Stands in for the module-level default DataClient."""

    def __init__(self, aggregate, package_list):
        self.aggregate = aggregate
        self._package_list = package_list

    def packages(self):
        return self.aggregate

    def package_list(self):
        return self._package_list

    def repository_info(self, owner_repo):
        return store.repository_entry(self.aggregate, owner_repo)


CHANDRA_ACA = {
    "name": "chandra_aca",
    "owner": "sot",
    "master_version": "1.2",
    "flight": "1.1",
    "test_status": "PASS",
}
KADI = {"name": "kadi", "owner": "sot", "master_version": "7.1"}
AGGREGATE = {
    "packages": [CHANDRA_ACA, KADI],
    "time": "2026-07-13T00:00:00",
    "record_options": {"since": 7},
}
PACKAGE_LIST = [
    {
        "name": "chandra_aca",
        "package": "chandra_aca",
        "repository": "sot/chandra_aca",
        "owner": "sot",
    }
]


@pytest.fixture()
def stored_data(monkeypatch):
    """Serve the public read API from a fake store, and forbid Github."""
    from skare3_tools.packages import packages as packages_module

    monkeypatch.setattr(
        packages_module, "_DEFAULT_CLIENT", FakeClient(AGGREGATE, PACKAGE_LIST)
    )

    def no_github(*args, **kwargs):
        raise AssertionError("must not query Github")

    monkeypatch.setattr(packages_module, "_repository_info_from_github", no_github)
    monkeypatch.setattr(packages_module, "_repositories_info_from_github", no_github)
    monkeypatch.setattr(packages_module, "_package_list_from_github", no_github)


@pytest.fixture()
def github_calls(monkeypatch):
    """Record calls to the direct-Github query instead of making them."""
    from skare3_tools.packages import packages as packages_module

    calls = []

    def fake(owner_repo, **kwargs):
        calls.append((owner_repo, kwargs))
        return {"name": owner_repo.split("/")[-1], "from_github": True}

    monkeypatch.setattr(packages_module, "_repository_info_from_github", fake)
    return calls


def test_get_repository_info_reads_the_store(stored_data):
    """The default read needs no token, and carries the deployment-stage fields."""
    info = packages.get_repository_info("sot/chandra_aca")
    assert info == CHANDRA_ACA
    assert info["master_version"] == "1.2"


def test_get_repository_info_queries_github_for_another_window(
    stored_data, github_calls
):
    """The store holds one rendering; a different `since` cannot come from it."""
    info = packages.get_repository_info("sot/chandra_aca", since="1.0.0")
    assert info["from_github"]
    assert github_calls == [("sot/chandra_aca", {"since": "1.0.0"})]


def test_get_repository_info_update_queries_github(stored_data, github_calls):
    packages.get_repository_info("sot/chandra_aca", update=True)
    assert github_calls == [("sot/chandra_aca", {})]


def test_get_repositories_info_reads_the_store(stored_data):
    assert packages.get_repositories_info() == AGGREGATE


def test_get_repositories_info_filters_to_the_requested_repositories(stored_data):
    info = packages.get_repositories_info(repositories=["sot/kadi"])
    assert info["packages"] == [KADI]
    assert info["time"] == AGGREGATE["time"]


def test_get_repositories_info_reports_unknown_repositories(stored_data, caplog):
    info = packages.get_repositories_info(repositories=["sot/kadi", "sot/nope"])
    assert info["packages"] == [KADI]
    assert "sot/nope" in caplog.text


def test_get_package_list_reads_the_store(stored_data):
    assert packages.get_package_list() == PACKAGE_LIST


def test_get_repository_info_accepts_the_stored_arguments(stored_data):
    """Spelling out what the store already holds must not trigger a query."""
    assert packages.get_repository_info("sot/chandra_aca", since=7) == CHANDRA_ACA


def test_get_repository_info_queries_github_when_options_unrecorded(
    monkeypatch, github_calls
):
    """An aggregate that does not say how it was made is not second-guessed."""
    from skare3_tools.packages import packages as packages_module

    aggregate = {k: v for k, v in AGGREGATE.items() if k != "record_options"}
    monkeypatch.setattr(
        packages_module, "_DEFAULT_CLIENT", FakeClient(aggregate, PACKAGE_LIST)
    )
    assert packages.get_repository_info("sot/chandra_aca", since=7)["from_github"]
    assert github_calls == [("sot/chandra_aca", {"since": 7})]


def test_skare3_recipes_are_fetched_to_a_temporary_directory(monkeypatch, tmp_path):
    """
    No checkout is left in the data directory.

    The recipes used to live in a git working tree inside the store, where they
    could go stale or be clobbered; a run now reads a tarball and leaves nothing
    behind.
    """
    import io
    import tarfile

    from skare3_tools.packages import packages as packages_module

    tarball = io.BytesIO()
    with tarfile.open(fileobj=tarball, mode="w:gz") as tar:
        recipe = tmp_path / "meta.yaml"
        recipe.write_text("package:\n  name: foo\n")
        tar.add(recipe, arcname="sot-skare3-abc123/pkg_defs/foo/meta.yaml")

    class FakeResponse:
        ok = True
        content = tarball.getvalue()

    monkeypatch.setattr(
        packages_module.github,
        "GITHUB_API_V3",
        type("A", (), {"get": lambda self, path: FakeResponse()})(),
    )
    with packages_module._skare3_recipes() as recipes:
        assert (recipes / "foo" / "meta.yaml").exists()
        leftover = recipes
    assert not leftover.exists()  # cleaned up on the way out


def test_unfetchable_recipes_are_not_silent(monkeypatch):
    """A failed fetch used to be swallowed, leaving stale recipes in place."""
    from skare3_tools.packages import packages as packages_module

    class FakeResponse:
        ok = False
        reason = "Not Found"
        status_code = 404

    monkeypatch.setattr(
        packages_module.github,
        "GITHUB_API_V3",
        type("A", (), {"get": lambda self, path: FakeResponse()})(),
    )
    with pytest.raises(packages.RecipesUnavailable, match="cannot fetch"):
        with packages_module._skare3_recipes():
            pass
