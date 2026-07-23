"""
Packaging checks.

The console-script check compares against whichever declaration matches the
code actually being tested:

- in a source checkout (pyproject.toml exists next to the package), the
  tree's ``[project.scripts]``. Installed entry-point metadata is frozen at
  install time, so after a branch switch it can disagree with the checked-out
  source and fail for scripts the current branch never declared.
- when the tests run from an installed package (e.g. under ska_testr, where
  there is no pyproject.toml), the installed metadata — which matches the
  installed code by construction.

Each declared target is imported directly either way.
"""

import tomllib
from importlib import import_module
from importlib.metadata import entry_points, version
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent.parent / "pyproject.toml"


def _declared_scripts():
    if PYPROJECT.exists():
        return tomllib.loads(PYPROJECT.read_text())["project"]["scripts"]
    return {
        e.name: e.value
        for e in entry_points(group="console_scripts")
        if e.name.startswith("skare3-")
    }


# These entry points import packages that are not in requirements.txt
# (cxotime, ska_file, conda_build — conda/ska-environment deps), so they
# are not imported in the minimal test environment. Scripts listed here but
# not declared in this branch's pyproject are simply never looked at.
OPTIONAL_DEP_SCRIPTS = {
    "skare3-refresh",
    "skare3-dashboard-update",
    "skare3-test-results",
    "skare3-test-report",
    "skare3-test-dashboard",
    "skare3-dashboard",
    "skare3-clone-git-repos",
    "skare3-fix-namespace-packages",
    "skare3-promote",
}


def test_console_scripts_declared_and_loadable():
    scripts = _declared_scripts()
    assert all(name.startswith("skare3-") for name in scripts)
    for name, target in sorted(scripts.items()):
        if name in OPTIONAL_DEP_SCRIPTS:
            continue
        module, attr = target.split(":")
        assert callable(getattr(import_module(module), attr)), name


def test_version_is_scm_derived():
    assert version("skare3_tools") not in ("", "0.0.0", None)
