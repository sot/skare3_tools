from importlib.metadata import entry_points, version

EXPECTED_SCRIPTS = {
    "skare3-build",
    "skare3-git-pass",
    "skare3-release-check",
    "skare3-test-results",
    "skare3-github-info",
    "skare3-changes-summary",
    "skare3-test-report",
    "skare3-dashboard",
    "skare3-test-dashboard",
    "skare3-bulk",
    "skare3-promote",
    "skare3-add-secrets",
    "skare3-create-issue",
    "skare3-create-pr",
    "skare3-merge-pr",
    "skare3-release-merge-info",
    "skare3-milestone-issues",
    "skare3-clone-git-repos",
    "skare3-fix-namespace-packages",
}

# These entry points import packages that are not in requirements.txt
# (cxotime, ska_file, conda_build — conda/ska-environment deps), so they
# are not load()-ed in the minimal test environment.
OPTIONAL_DEP_SCRIPTS = {
    "skare3-test-results",
    "skare3-test-report",
    "skare3-test-dashboard",
    "skare3-dashboard",
    "skare3-clone-git-repos",
    "skare3-fix-namespace-packages",
    "skare3-promote",
}


def test_console_scripts_present_and_loadable():
    eps = {
        e.name: e
        for e in entry_points(group="console_scripts")
        if e.name.startswith("skare3-")
    }
    assert set(eps) == EXPECTED_SCRIPTS
    for name in sorted(EXPECTED_SCRIPTS - OPTIONAL_DEP_SCRIPTS):
        eps[name].load()


def test_version_is_scm_derived():
    assert version("skare3_tools") not in ("", "0.0.0", None)
