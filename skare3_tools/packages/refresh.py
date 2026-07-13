"""
``skare3-refresh``: the single writer of the package-data store.

One run brings the store (see :mod:`skare3_tools.packages.store`) up to date:

1. refresh the package list (skare3 pkg_defs + org repositories),
2. snapshot the conda channels once and resolve the four metapackages
   (ska3-aca/flight/matlab/perl) — failing loudly if any can't be resolved,
3. detect changed repositories with one batched GraphQL query and fetch
   detail only for those,
4. rebuild ``packages.json`` (always — metapackage pins and channel versions
   can change without any repository push), digest the latest test results,
   and advance ``meta/state.json`` last, so an interrupted run only causes a
   refetch.

Authentication: with ``SKARE3_GITHUB_APP_KEY`` set, per-org installation
tokens are minted for GitHub App 77359; otherwise the usual
``GITHUB_API_TOKEN``/``GITHUB_TOKEN`` PAT is used for both orgs. Note that
installation tokens are org-scoped: cross-org listings only see public
repositories, which all Ska repositories are.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from skare3_tools import test_results
from skare3_tools.config import CONFIG
from skare3_tools.github import github, graphql
from skare3_tools.packages import packages, store

logger = logging.getLogger("skare3.refresh")

METAPACKAGES = ("ska3-aca", "ska3-flight", "ska3-matlab", "ska3-perl")
# metapackages whose members count as "ska packages" (perl is recorded only)
SKA_METAPACKAGES = ("ska3-aca", "ska3-flight", "ska3-matlab")


class RefreshError(Exception):
    """The store could not be refreshed; nothing was written."""


def resolve_metapackages(conda_info):
    """
    Resolve version and member pins of every metapackage.

    :param conda_info: dict. A whole-channel conda search result
        (``get_conda_pkg_info("*", ...)``).
    :return: dict. ``{"ska3-aca": {"version": ..., "pins": {pkg: version}}, ...}``
    :raises RefreshError: if any metapackage is missing from the channel.
    """
    meta = {}
    for name in METAPACKAGES:
        if not conda_info.get(name):
            raise RefreshError(f"metapackage {name} not found in the conda channel")
        latest = conda_info[name][-1]
        meta[name] = {"version": latest["version"], "pins": latest["depends"]}
    return meta


def _resolve_tokens(organizations):
    """One GitHub token per org: App installation tokens, or the PAT for all."""
    if os.environ.get("SKARE3_GITHUB_APP_KEY"):
        from skare3_tools.github import app_auth

        installations = app_auth.get_installations()
        tokens = {}
        for org in organizations:
            if org not in installations:
                raise RefreshError(f"GitHub App is not installed on org {org}")
            tokens[org] = app_auth.get_installation_token(installations[org])["token"]
        return tokens
    # PAT (possibly None: the wrappers then use whatever they already have)
    token = os.environ.get("GITHUB_API_TOKEN") or os.environ.get("GITHUB_TOKEN")
    return dict.fromkeys(organizations, token)


def _metapackage_fields(conda_package, metapackages):
    """The per-package metapackage model: flat pins, membership dict, is_ska."""
    fields = {}
    membership = {}
    for name in METAPACKAGES:
        pins = metapackages[name]["pins"]
        short = name.replace("ska3-", "")
        member = conda_package is not None and conda_package in pins
        fields[short] = pins.get(conda_package, "") if member else ""
        if member:
            membership[name] = pins[conda_package]
    fields["metapackages"] = membership
    fields["is_ska"] = any(name in membership for name in SKA_METAPACKAGES)
    return fields


def _test_summary(test_run, repo2name):
    """
    Per-repository test version/status from the latest test run.

    Same logic the dashboard used to apply on the fly (PASS unless something
    failed; SKIP when everything was skipped).
    """
    summary = {}
    suites = test_run.get("test_suites", [])
    for repo, name in repo2name.items():
        package_tests = [ts for ts in suites if ts["package"] == name]
        if not package_tests:
            continue
        status = [tc["status"] for ts in package_tests for tc in ts["test_cases"]]
        if any(s == "fail" for s in status):
            test_status = "FAIL"
        elif all(s == "skipped" for s in status):
            test_status = "SKIP"
        else:
            test_status = "PASS"
        summary[repo] = {
            "test_version": package_tests[0]["properties"]["package_version"],
            "test_status": test_status,
        }
    return summary


def _read_state(directory):
    try:
        with open(directory / "meta" / "state.json") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _latest_test_run(stream):
    try:
        return test_results.get_latest(stream=stream)
    except FileNotFoundError:
        logger.warning("no test results found for stream %s", stream)
        return {}


def refresh(data_dir=None, full=False, stream="ska3-masters", tokens=None):
    """
    Refresh the data store. Returns a summary dict.

    :param data_dir: store directory (default: the configured store root).
    :param full: bool. Refetch every repository, ignoring change detection.
    :param stream: str. Test-results stream baked into the aggregate.
    :param tokens: dict. org -> token; resolved from the environment when
        None. A None token means "leave the API singletons as they are"
        (used in tests).
    :return: dict with "written", "skipped" and "failures".
    """
    directory = Path(data_dir) if data_dir else store.store_dir()
    organizations = CONFIG["organizations"]
    deprecated = set(CONFIG.get("deprecated_repositories", []))
    if tokens is None:
        tokens = _resolve_tokens(organizations)

    with store.StoreLock(directory):
        state = _read_state(directory)

        # the package universe: pkg_defs + org repos, minus deprecated
        first_org = organizations[0]
        if tokens.get(first_org):
            github.init(token=tokens[first_org])
        pkg_list = packages.get_package_list(update=True)
        pkg_list = [
            p
            for p in pkg_list
            if p["owner"] in organizations and p["repository"] not in deprecated
        ]
        repo_package_map = {p["repository"]: p["package"] for p in pkg_list}
        repo2name = {p["repository"]: p["name"] for p in pkg_list}
        universe = sorted(repo_package_map)

        # one conda snapshot per channel; metapackages must resolve (loudly)
        conda_main = packages.get_conda_pkg_info("*", conda_channel="main")
        conda_masters = packages.get_conda_pkg_info("*", conda_channel="masters")
        metapackages = resolve_metapackages(conda_main)

        # change detection: one batched query instead of per-repo round trips
        last_updated = graphql.get_last_updated(universe)
        state_repos = state.get("repos", {})
        summary = {"written": [], "skipped": [], "failures": {}}
        by_org = {org: [] for org in organizations}
        for owner_repo in universe:
            org = owner_repo.split("/")[0]
            repo_file = _repo_file(directory, owner_repo)
            if (
                not full
                and repo_file.exists()
                and last_updated.get(owner_repo) is not None
                and state_repos.get(owner_repo) == last_updated[owner_repo]
            ):
                summary["skipped"].append(owner_repo)
            else:
                by_org[org].append(owner_repo)

        for org in organizations:
            if not by_org[org]:
                continue
            if tokens.get(org):
                github.init(token=tokens[org])
            for owner_repo in by_org[org]:
                try:
                    info = packages._get_repository_info_v4(owner_repo)
                except Exception as exc:
                    logger.error("failed to fetch %s: %s", owner_repo, exc)
                    summary["failures"][owner_repo] = str(exc)
                    continue
                store.atomic_write_json(_repo_file(directory, owner_repo), info)
                state_repos[owner_repo] = last_updated.get(owner_repo)
                summary["written"].append(owner_repo)

        # the aggregate is always rebuilt: channel versions and metapackage
        # pins move without any repository push
        test_run = _latest_test_run(stream)
        tests = _test_summary(test_run, repo2name)
        info = {
            "schema_version": store.SCHEMA_VERSION,
            "time": datetime.now(timezone.utc).isoformat(),
            "ska3-flight": metapackages["ska3-flight"]["version"],
            "ska3-matlab": metapackages["ska3-matlab"]["version"],
            "metapackages": {
                name: metapackages[name]["version"] for name in METAPACKAGES
            },
            "packages": [],
        }
        for owner_repo in universe:
            repo_file = _repo_file(directory, owner_repo)
            if not repo_file.exists():
                logger.warning("no data for %s, not in the aggregate", owner_repo)
                continue
            with open(repo_file) as fh:
                pkg = json.load(fh)
            name = pkg["name"]
            masters_entry = conda_masters.get(name.lower())
            pkg["master_version"] = (
                masters_entry[-1]["version"] if masters_entry else ""
            )
            pkg.update(_metapackage_fields(repo_package_map[owner_repo], metapackages))
            pkg.update(tests.get(owner_repo, {"test_version": "", "test_status": ""}))
            info["packages"].append(pkg)
        info["packages"].sort(key=lambda p: p["name"])

        store.atomic_write_json(directory / "packages.json", info)
        if test_run:
            from skare3_tools.dashboard.views.test_results import _get_results

            store.atomic_write_json(
                directory / "test_results.json",
                _get_results(test_run, config=None, render=False),
            )
        store.atomic_write_json(
            directory / "manifest.json",
            {
                "schema_version": store.SCHEMA_VERSION,
                "generated": info["time"],
                "producer": _producer_id(),
                "excluded": sorted(deprecated),
                "skare3_tools_version": _version(),
            },
        )
        # state last: a crash before this point only causes a refetch
        state.update(
            {
                "repos": state_repos,
                "last_run": info["time"],
                **({"last_full_refresh": info["time"]} if full else {}),
            }
        )
        store.atomic_write_json(directory / "meta" / "state.json", state)

    return summary


def _repo_file(directory, owner_repo):
    owner, name = owner_repo.split("/")
    return directory / "repos" / owner / f"{name}.json"


def _producer_id():
    if os.environ.get("SKARE3_GITHUB_APP_KEY"):
        from skare3_tools.github.app_auth import APP_ID

        return f"app:{APP_ID}"
    return "token"


def _version():
    try:
        return metadata.version("skare3_tools")
    except metadata.PackageNotFoundError:
        return ""


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--data-dir", type=Path, help="Store directory (for scratch runs)"
    )
    parser.add_argument("--full", action="store_true", help="Refetch all repositories")
    parser.add_argument("--stream", default="ska3-masters", help="Test-results stream")
    parser.add_argument(
        "--ingest-tests",
        metavar="DIR",
        type=Path,
        help="Ingest a testr output directory before refreshing",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main():
    args = get_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.ingest_tests:
        test_results.add(str(args.ingest_tests), stream=args.stream)
    try:
        summary = refresh(data_dir=args.data_dir, full=args.full, stream=args.stream)
    except (RefreshError, store.StoreLockedError) as exc:
        sys.exit(f"refresh failed: {exc}")
    logger.info(
        "refreshed: %s updated, %s unchanged",
        len(summary["written"]),
        len(summary["skipped"]),
    )
    if summary["failures"]:
        sys.exit(
            "failed to fetch:\n"
            + "\n".join(f"  {k}: {v}" for k, v in summary["failures"].items())
        )


if __name__ == "__main__":
    main()
