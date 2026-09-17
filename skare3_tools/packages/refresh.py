"""
The single writer of the package-data store.

The command-line entry point is :mod:`skare3_tools.scripts.refresh`
(``skare3-refresh``).

One run brings the store (see :mod:`skare3_tools.packages.store`) up to date:

1. refresh the package list (the skare3 recipes, fetched to a temporary
   directory, plus the org repositories) into ``package_list.json``, and take
   the working universe from it, excluding repositories listed in
   ``repository_status.json`` at the store root — an operator-edited file that
   refresh seeds once if missing and never overwrites,
2. snapshot the conda channels once and resolve the four metapackages
   (ska3-aca/flight/matlab/perl) — failing loudly if any can't be resolved,
3. detect changed repositories with one batched GraphQL query and fetch detail
   only for those, carrying the rest over from the previous ``packages.json``
   (the aggregate is the incremental cache as well as the output — there is no
   second copy of a repository's record anywhere),
4. rebuild ``packages.json`` (always — metapackage pins and channel versions
   can change without any repository push), digest the latest test results,
   and advance ``meta/state.json`` last, so an interrupted run only causes a
   refetch.

If there is no readable test run, the tested versions already in the store are
kept rather than blanked, and the run is reported as a failure: an aggregate
claiming nothing was tested is indistinguishable from the truth once written.

If the conda channels or GitHub cannot be reached at all, the run aborts with
:class:`RefreshError` before writing anything: the store keeps the data it has.

Authentication is entirely the github wrappers' business: a personal token
(``GITHUB_API_TOKEN``/``GITHUB_TOKEN``) or, when ``SKARE3_GITHUB_APP_KEY`` is
set, per-organization App-77359 installation tokens minted transparently per
request (see :mod:`skare3_tools.github.app_auth`).
"""

import json
import logging
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import requests

from skare3_tools import test_results
from skare3_tools.config import CONFIG
from skare3_tools.github import graphql
from skare3_tools.github.github import AuthException
from skare3_tools.packages import packages, store

logger = logging.getLogger("skare3.refresh")

METAPACKAGES = ("ska3-aca", "ska3-flight", "ska3-matlab", "ska3-perl")
# metapackages whose members count as "ska packages" (perl is recorded only)
SKA_METAPACKAGES = ("ska3-aca", "ska3-flight", "ska3-matlab")

# initial repository_status.json, written only if the file does not exist;
# after that the file is operator-edited input and refresh never writes it
INITIAL_REPOSITORY_STATUS = {
    "sot/skare": "deprecated",
    "sot/test-actions": "ignored",  # workflow-testing sandbox: alive, but not a package
    "acisops/dpa_check": "deprecated",
    "acisops/psmc_check": "deprecated",
    "acisops/acisfp_check": "deprecated",
    "acisops/fep1_mong_check": "deprecated",
    "acisops/fep1_actel_check": "deprecated",
    "acisops/bep_pcb_check": "deprecated",
}


# the dashboard's spelling of test_results.summary_status
_TEST_STATUS = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP"}

# GitHub could not be asked: no network, or credentials that are missing or
# refused. Anything else raised while talking to it is a bug, and propagates.
_GITHUB_UNAVAILABLE = (
    requests.RequestException,
    graphql.GithubException,
    AuthException,
)


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

    The status comes from the per-case statuses, not from the per-suite status
    stored with the run: runs ingested by older versions of test_results.add()
    carry a suite status that never says "fail".
    """
    summary = {}
    suites = test_run.get("test_suites", [])
    for repo, name in repo2name.items():
        package_tests = [ts for ts in suites if ts["package"] == name]
        if not package_tests:
            continue
        status = [tc["status"] for ts in package_tests for tc in ts["test_cases"]]
        summary[repo] = {
            "test_version": package_tests[0]["properties"]["package_version"],
            "test_status": _TEST_STATUS[test_results.summary_status(status)],
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


def refresh(data_dir=None, full=False, stream="ska3-masters"):
    """
    Refresh the data store. Returns a summary dict.

    :param data_dir: store directory (default: the configured store root).
    :param full: bool. Refetch every repository, ignoring change detection.
    :param stream: str. Test-results stream baked into the aggregate.
    :return: dict with "written", "skipped" and "failures".
    """
    directory = Path(data_dir) if data_dir else store.store_dir()
    organizations = CONFIG["organizations"]

    with store.StoreLock(directory):
        status_file = directory / "repository_status.json"
        if not status_file.exists():
            store.atomic_write_json(status_file, INITIAL_REPOSITORY_STATUS)
            logger.info(
                "seeded %s with %d repositories",
                status_file,
                len(INITIAL_REPOSITORY_STATUS),
            )
        try:
            repository_status = store.repository_status(directory)
        except ValueError as exc:
            raise RefreshError(str(exc)) from None
        excluded = set(repository_status)

        state = _read_state(directory)
        summary = {"written": [], "skipped": [], "failures": {}}

        # the package universe: recipes + org repos, minus excluded statuses.
        # the unfiltered list is what goes in the store: consumers resolving an
        # old metapackage version need packages of deprecated repositories too
        full_pkg_list, fetched_pkg_list = _package_list(directory, summary)
        pkg_list = [
            p
            for p in full_pkg_list
            if p["owner"] in organizations and p["repository"] not in excluded
        ]
        repo_package_map = {p["repository"]: p["package"] for p in pkg_list}
        repo2name = {p["repository"]: p["name"] for p in pkg_list}
        universe = sorted(repo_package_map)

        # one conda snapshot per channel; metapackages must resolve (loudly)
        try:
            conda_main = packages.get_conda_pkg_info("*", conda_channel="main")
            conda_masters = packages.get_conda_pkg_info("*", conda_channel="masters")
        except packages.NetworkException as exc:
            raise RefreshError(str(exc)) from exc
        metapackages = resolve_metapackages(conda_main)

        # change detection: batched queries instead of per-repo round trips
        try:
            last_updated = graphql.get_last_updated(universe)
        except _GITHUB_UNAVAILABLE as exc:
            raise RefreshError(f"could not detect changed repositories: {exc}") from exc
        state_repos = state.get("repos", {})
        previous = _previous_records(directory)
        records = {}
        for owner_repo in universe:
            cached = previous.get(owner_repo)
            if (
                not full
                and cached is not None
                and last_updated.get(owner_repo) is not None
                and state_repos.get(owner_repo) == last_updated[owner_repo]
            ):
                records[owner_repo] = cached
                summary["skipped"].append(owner_repo)
                continue
            try:
                records[owner_repo] = packages._get_repository_info_v4(owner_repo)
            except Exception as exc:
                logger.error("failed to fetch %s: %s", owner_repo, exc)
                summary["failures"][owner_repo] = str(exc)
                if cached is not None:
                    # keep the previous good record. state is not advanced, so
                    # the next run retries this repository
                    records[owner_repo] = cached
                continue
            state_repos[owner_repo] = last_updated.get(owner_repo)
            summary["written"].append(owner_repo)

        # the aggregate is always rebuilt: channel versions and metapackage
        # pins move without any repository push
        test_run = _latest_test_run(stream)
        tests = _test_summary(test_run, repo2name)
        if not test_run:
            # loudly: silently blanking the test status of every package looks
            # exactly like "nothing has been tested", which is a lie the
            # dashboard has no way to distinguish from the truth
            summary["failures"][f"test results ({stream})"] = (
                "no readable test run; the tested versions of every package are "
                "left as they were"
            )
        info = {
            "schema_version": store.SCHEMA_VERSION,
            "time": datetime.now(timezone.utc).isoformat(),
            "ska3-flight": metapackages["ska3-flight"]["version"],
            "ska3-matlab": metapackages["ska3-matlab"]["version"],
            "metapackages": {
                name: metapackages[name]["version"] for name in METAPACKAGES
            },
            "record_version": store.RECORD_VERSION,
            "record_options": packages.record_options(),
            "packages": [],
        }
        # every repository is enriched every run, including the ones skipped
        # above: the deployment-stage fields (master/flight/matlab/aca and the
        # test versions) move with the channels and the test runs, not with
        # repository pushes. Do not fold this into the fetch loop -- that would
        # freeze those fields for unchanged repositories. Reuse is safe only
        # because every field below is assigned unconditionally.
        for owner_repo in universe:
            if owner_repo not in records:
                logger.warning("no data for %s, not in the aggregate", owner_repo)
                continue
            pkg = dict(records[owner_repo])
            name = pkg["name"]
            masters_entry = conda_masters.get(name.lower())
            pkg["master_version"] = (
                masters_entry[-1]["version"] if masters_entry else ""
            )
            pkg.update(_metapackage_fields(repo_package_map[owner_repo], metapackages))
            if test_run:
                # a readable run: a package it does not mention was not tested
                pkg.update(
                    tests.get(owner_repo, {"test_version": "", "test_status": ""})
                )
            else:
                # nothing readable to say what was tested: keep what the last
                # run recorded rather than asserting "not tested" (reported in
                # the summary above). They come from the stored record because
                # a refetched one has no test fields at all
                stored = previous.get(owner_repo, {})
                pkg["test_version"] = stored.get("test_version", "")
                pkg["test_status"] = stored.get("test_status", "")
            info["packages"].append(pkg)
        info["packages"].sort(key=lambda p: p["name"])

        store.atomic_write_json(directory / "packages.json", info)
        if fetched_pkg_list:
            store.atomic_write_json(
                directory / "package_list.json",
                {
                    "schema_version": store.SCHEMA_VERSION,
                    "time": info["time"],
                    "package_list": full_pkg_list,
                },
            )
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
                "excluded": sorted(excluded),
                "repository_status": repository_status,
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


def _package_list(directory, summary):
    """
    The package universe, and whether it came from the recipes.

    The recipes are the authority, but they need a network fetch. If that
    fails, the store's own ``package_list.json`` is the parsed product of an
    earlier fetch and stands in for them -- reported as a failure, so the run
    is not quietly built on an older universe. With neither, there is no
    universe and nothing worth writing.

    :return: (list, bool). The package list, and True if it was just fetched.
    """
    try:
        return packages._package_list_from_github(), True
    except packages.RecipesUnavailable as exc:
        stored = _previous_package_list(directory)
        if stored is None:
            raise RefreshError(f"{exc}, and the store has no package list") from None
        logger.error("%s; falling back to the stored package list", exc)
        summary["failures"]["package list"] = (
            f"{exc}; used the package list already in the store"
        )
        return stored, False


def _previous_package_list(directory):
    """The package list in the store, or None if there is not one."""
    try:
        with open(directory / "package_list.json") as fh:
            return json.load(fh)["package_list"]
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def _previous_records(directory):
    """
    The per-repository records of the existing aggregate, keyed "owner/name".

    ``packages.json`` is both the output and the incremental cache: records of
    repositories GitHub reports unchanged are carried over from it instead of
    being refetched. A missing or unreadable aggregate yields {}, so everything
    is fetched again.

    What disqualifies the records is a change in their own shape -- a different
    ``record_version`` or different ``record_options`` -- not the store's
    layout. An aggregate written by an older ``schema_version`` is still a
    perfectly good source of records, and refetching every repository because
    the surrounding files moved would cost thousands of queries for nothing.
    """
    try:
        with open(directory / "packages.json") as fh:
            aggregate = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    # aggregates written before the field existed carry record shape 1
    version = aggregate.get("record_version", 1)
    if version != store.RECORD_VERSION:
        logger.info(
            "aggregate holds record version %s, not %s: fetching every repository",
            version,
            store.RECORD_VERSION,
        )
        return {}
    stored_options = aggregate.get("record_options")
    if stored_options is not None and stored_options != packages.record_options():
        logger.info(
            "aggregate was made with %s, not %s: fetching every repository",
            stored_options,
            packages.record_options(),
        )
        return {}
    return {f"{p['owner']}/{p['name']}": p for p in aggregate.get("packages", [])}


def _producer_id():
    from skare3_tools.github import app_auth

    settings = app_auth.app_settings()
    if settings["key_path"]:
        return f"app:{settings['app_id']}"
    return "token"


def _version():
    try:
        return metadata.version("skare3_tools")
    except metadata.PackageNotFoundError:
        return ""
