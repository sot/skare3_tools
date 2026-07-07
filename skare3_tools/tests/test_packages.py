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
    assert foo["repository"] == "sot/foo"   # full owner/repo, from about.home
    assert foo["owner"] == "sot"
    assert foo["package"] == "foo"
    assert by_name["nohome"]["repository"] is None   # no about.home -> no repo
    assert by_name["nohome"]["owner"] is None
    # extra org repo appended even though it has no pkg_def
    assert any(
        p["repository"] == "sot/bar" and p["package"] is None for p in result
    )
    # sorted output (matches production sort key: repository-or-"" then name)
    keys = [((p["repository"] or ""), p["name"]) for p in result]
    assert keys == sorted(keys)


def test_get_package_list_skips_bad_recipe(monkeypatch, fake_skare3_repo):
    monkeypatch.setattr(packages.github, "Organization", FakeOrganization)
    result = packages.get_package_list(update=True)   # badpkg present in fixtures
    assert all(p["name"] != "badpkg" for p in result)  # skipped, not raised
