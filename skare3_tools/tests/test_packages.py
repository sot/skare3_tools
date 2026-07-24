"""
Characterize packages.get_package_list (skare3_tools/packages.py:239-315).

The audited contract: each entry is a dict with keys name / package / repository /
owner; a recipe with no ``about.home`` yields repository/owner None; organization
repositories with no local pkg_def are appended; the result is sorted.

Adjust-to-reality notes (pinned against packages.py while writing):
- ``repository`` is the *full* ``owner/repo`` string, not the bare repo name.
  ``_conda_package_list`` sets ``pkg_info["repository"] = "{org}/{repo}"``
  (packages.py:277), so foo -> "sot/foo".
- The org protocol: ``get_package_list`` calls ``org.repositories()`` and reads
  ``r["full_name"]`` and ``r["owner"]["login"]`` (packages.py:299-309), so the
  fake must return dicts keyed by ``full_name`` (not ``name``).
"""

import pytest

from skare3_tools import packages


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
        "repository_info_is_outdated",
        "json_cache",
        "NetworkException",
        "get_parser",
        "main",
        "_get_release_commit",  # used by github/scripts/release_merge_info.py
    ]:
        assert getattr(packages, name) is not None
    assert packages.github is not None  # patched by tests via packages.github


def test_get_repositories_info_is_deprecated():
    with pytest.warns(DeprecationWarning, match="DataClient"):
        packages.get_repositories_info(repositories=[])


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
