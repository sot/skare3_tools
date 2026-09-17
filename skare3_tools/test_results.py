#!/usr/bin/env python3
"""
A very primitive database of test results.

It is assumed that test results are grouped in "test suites", which are just a group of
tests run together.

Tests are grouped in "streams" which can be viewed as the same set of tests performed repeatedly
For example: daily regression tests can be a stream, unit tests upon merging to master can be
another, and release tests can be yet another. All test suites can also be given "tags" that allow
a more arbitrary grouping.

To add a test suite to the database, one normally uses the :ref:`skare3-test-results` script,
which basically does this::

    >>> from skare3_tools import test_results
    >>> test_results.add('test_logs/', stream='ska3-masters')

And to retrieve all tests for a stream::

    >>> from skare3_tools import test_results
    >>> test_results.get(stream='ska3-masters')


"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skare3_tools import config


class TestResultException(Exception):
    pass


# per-case statuses testr reports for a test that did not pass. An error means
# the test could not run to the end (a broken fixture, a failed import), so it
# counts as a failure.
FAILED_STATUSES = ("fail", "error")


def summary_status(case_statuses):
    """
    The status of a group of test cases: one of "pass", "fail" or "skipped".

    This is the one place deciding what a test suite (or a package) passing
    means: it fails if any case failed or errored, it is skipped if every case
    was skipped, and it passes otherwise.

    :param case_statuses: list of the per-case statuses testr reports
        ("pass", "fail", "error" or "skipped").
    :return: str
    """
    if any(s in FAILED_STATUSES for s in case_statuses):
        return "fail"
    if all(s == "skipped" for s in case_statuses):
        return "skipped"
    return "pass"


def _test_data_dir():
    """The test-results store, resolved from the configuration at call time."""
    return Path(config.data_dir()).absolute() / "test_logs"


def _index_file():
    return _test_data_dir() / "index.json"


def _ensure_store():
    """Create the store on first write (readers get FileNotFoundError)."""
    _test_data_dir().mkdir(parents=True, exist_ok=True)
    if not _index_file().exists():
        _index_file().write_text("[]")


LOGGER = logging.getLogger("skare3_tools")


def remove(uid=None, directory=None, uids=(), directories=()):
    with open(_index_file(), "r") as fh:
        test_result_index = json.load(fh)

    uids = list(uids)
    if uid and uid not in uids:
        uids += [uid]

    directories = [_test_data_dir() / directory for directory in directories]
    if directory and directory not in directories:
        directories += [_test_data_dir() / directory]

    # make sure all directories are absolute and within the data tree
    for drctry in directories:
        if _test_data_dir() not in drctry.resolve().parents:
            LOGGER.warning(f"warning: {drctry} not in SKARE3_DASH_DATA. Ignoring")
    directories = [
        drctry for drctry in directories if _test_data_dir() in drctry.resolve().parents
    ]

    # make a list of everything that will be removed
    rm = [
        tr
        for tr in test_result_index
        if tr["uid"] in uids or _test_data_dir() / tr["destination"] in directories
    ]

    for tr in rm:
        test_result_index.remove(tr)
        # the index outlives the runs it references, so the directory can
        # already be gone (see _read_run); the entry still goes
        run_dir = _test_data_dir() / tr["destination"]
        if run_dir.exists():
            shutil.rmtree(run_dir)

    for drctry in directories:
        if drctry.exists():
            LOGGER.warning(
                f"The directory {drctry} is still there."
                "This does not happen unless the directory is already not in the index,"
                "in which case it is safe to remove it by hand."
            )

    with open(_index_file(), "w") as fh:
        json.dump(test_result_index, fh, indent=2)


def remove_older_than(days):
    """
    Remove all the test results older than the given number of days.

    The date comes from the index entry's directory name (see _run_date), so a
    run that is no longer on disk still ages out of the index, and no run needs
    to be read to prune it. An entry with no usable date is left alone: refusing
    to prune is safe, deleting on a guess is not.
    """
    # testr writes UTC (runs from before it did are off by a few hours, which a
    # cutoff in days does not care about)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    expired = []
    for entry in _matching_entries():
        date = _parse_run_date(_run_date(entry))
        if date is None:
            LOGGER.warning("not pruning %s: no date in its name", entry["destination"])
        elif date < cutoff:
            expired.append(entry["uid"])

    if expired:
        remove(uids=expired)


def add(directory, stream, tags=(), properties=None):
    """
    Add the test results from a given directory to the database.

    :param directory:
    :param stream: str
    :param tags: list
    :param properties: dict.
        Other properties to store about this test suite.
    :return:
    """
    if properties is None:
        properties = {}
    _ensure_store()
    directory = Path(directory)
    if not directory.exists():
        raise TestResultException(
            'Directory "{directory}" does not exist'.format(directory=directory)
        )

    all_test_log = directory / "all_tests.json"
    if not all_test_log.exists():
        raise TestResultException(
            "Not importing: all_tests.json not found in {directory}".format(
                directory=directory
            )
        )

    with open(all_test_log) as f:
        uid = hashlib.md5(f.read().encode()).hexdigest()

    with open(_index_file(), "r") as f:
        test_result_index = json.load(f)

    if uid in [r["uid"] for r in test_result_index]:
        raise TestResultException("These test results already exist")

    all_test_log = directory / "all_tests.json"
    with open(all_test_log) as f:
        test_suites = json.load(f)

    date = test_suites["run_info"]["date"]
    destination = "{stream}_{date}_{uid}".format(stream=stream, date=date, uid=uid)
    abs_destination = _test_data_dir() / destination
    if abs_destination.exists():
        raise Exception(f"Destination already exists: {abs_destination}")

    # architecture, system, hostname and platform are stored as lists in the testr output file
    # and this "fixes that", at the expense of changing the format.
    test_suites["run_info"]["system"] = " ".join(test_suites["run_info"]["system"])
    test_suites["run_info"]["architecture"] = " ".join(
        test_suites["run_info"]["architecture"]
    )
    test_suites["run_info"]["hostname"] = " ".join(test_suites["run_info"]["hostname"])
    test_suites["run_info"]["platform"] = " ".join(test_suites["run_info"]["platform"])

    for ts in test_suites["test_suites"]:
        # count by the per-case status testr reports (the "skipped"/"failure"
        # sub-dicts only carry messages and are not present on passing cases)
        status = [tc.get("status") for tc in ts["test_cases"]]
        ts["n_skip"] = status.count("skipped")
        ts["n_fail"] = sum(status.count(s) for s in FAILED_STATUSES)
        ts["n_pass"] = status.count("pass")
        ts["status"] = summary_status(status)

        ts["properties"].update(properties)
        ts["properties"]["tags"] = tags
        ts["properties"]["stream"] = stream
        ts["properties"]["uid"] = uid

        for tc in ts["test_cases"]:
            tc["err_message"] = ""
            tc["err_output"] = ""
            for k in ["skipped", "failure"]:
                if k in tc:
                    tc["err_message"] = tc[k]["message"]
                    tc["err_output"] = tc[k]["output"]
                    break
            tc["skip"] = "skipped" in tc
            tc["failure"] = "failure" in tc

    result = {
        "uid": uid,
        "destination": destination,
        "stream": stream,
        "tags": tags,
        "properties": properties,
    }
    result.update(
        {
            k: sorted({ts["properties"][k] for ts in test_suites["test_suites"]})
            for k in ["architecture", "hostname", "system", "platform"]
        }
    )
    test_result_index.append(result)

    # copying to a temporary directory first, to make sure there are no surprises
    with tempfile.TemporaryDirectory() as tmpdirname:
        tmp_destination = Path(tmpdirname) / destination
        shutil.copytree(directory, tmp_destination, ignore=_ignore_unreadable)
        shutil.copy(all_test_log, tmp_destination / (all_test_log.name + ".orig"))
        with open(tmp_destination / all_test_log.name, "w") as f:
            json.dump(test_suites, f, indent=2)

        # after that succeeded, copy to the final destination (which does not exist yet)
        shutil.copytree(
            tmp_destination,
            abs_destination,
        )

    with open(_index_file(), "w") as f:
        json.dump(test_result_index, f, indent=2)

    # update the symbolic link pointing to the latest test in the stream
    symlink = _test_data_dir() / stream

    symlink.unlink(missing_ok=True)
    symlink.symlink_to(abs_destination)


def _ignore_unreadable(src, names):
    # this is used in shutil.copytree to ignore files that are not readable due to permissions
    return [name for name in names if not os.access(os.path.join(src, name), os.R_OK)]


def _matching_entries(stream=None, architecture=None, tag=None, system=None):
    """The index entries matching the given filters, in index order."""
    with open(_index_file(), "r") as f:
        test_result_index = json.load(f)
    return [
        tr
        for tr in test_result_index
        if not (
            (stream and stream not in tr["stream"])
            or (architecture and architecture not in tr["architecture"])
            or (tag and tag not in tr["tag"])
            or (system and system not in tr["system"])
        )
    ]


def _run_date(entry):
    """
    The run date of an index entry, taken from its directory name.

    ``add`` builds the name as ``{stream}_{date}_{uid}``, so the date can be
    read without opening the run itself. An unrecognizable name gives "".
    """
    name, prefix, suffix = (
        entry["destination"],
        entry["stream"] + "_",
        "_" + entry["uid"],
    )
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix) : -len(suffix)]
    return ""


# testr writes ISO 8601. Until 2026-09 it wrote a colon-separated variant
# (%Y:%m:%dT%H:%M:%S), which the runs already in the store still carry, so both
# are read. The two do not sort the same way as text ("-" < ":"), which is why
# runs are ordered by the parsed date and not by name.
_RUN_DATE_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y:%m:%dT%H:%M:%S")


def _parse_run_date(date):
    """The run date as a datetime, or None if it is in no format we know."""
    for date_format in _RUN_DATE_FORMATS:
        try:
            return datetime.strptime(date, date_format)
        except ValueError:
            continue
    return None


def _sort_key(date):
    """Order by parsed date, sorting anything undatable oldest."""
    return _parse_run_date(date) or datetime.min


def _read_run(entry):
    """
    The test run an index entry points at, or None if it cannot be read.

    The index outlives the runs it references: ``remove_older_than`` prunes
    directories, and a partially copied store has fewer runs than entries. A
    missing run is therefore an expected state, not an error.
    """
    all_test_log = _test_data_dir() / entry["destination"] / "all_tests.json"
    try:
        with open(all_test_log) as f:
            run = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("skipping test run %s: %s", entry["destination"], exc)
        return None
    run.setdefault("run_info", {})
    run["run_info"] = {**entry, **run["run_info"]}
    return run


def get(stream=None, architecture=None, tag=None, system=None):
    """
    Get all the test results for the given stream, architecture, tag and system sorted by date.

    Index entries whose run is no longer on disk are skipped with a warning.

    :param stream: str
    :param architecture: str
    :param tag: str
    :param system: str
    :return: list
    """
    entries = _matching_entries(stream, architecture, tag, system)
    result = [run for run in (_read_run(tr) for tr in entries) if run is not None]
    return sorted(result, key=lambda r: _sort_key(r["run_info"]["date"]))


def get_latest(stream=None, architecture=None, tag=None, system=None):
    """
    Get the latest test results for the given stream, architecture, tag and system.

    Only the newest run is read. Reading every indexed run just to return one
    is both slow (hundreds of files) and fragile: a single pruned run used to
    make this fail entirely. Entries are tried newest first, so the answer is
    the newest run that is actually readable, and {} if none is.

    Note this is one run, not the latest result *per package*: testr run with
    ``--include``/``--exclude`` produces runs covering only some packages, and
    a package missing from the newest run reads as untested. That has always
    been the behaviour here. Merging results across runs would need each one
    to carry which run it came from and when, so that a stale pass is not
    displayed as a current one -- without that, silently filling the gaps is
    worse than leaving them visible.

    :param stream: str
    :param architecture: str
    :param tag: str
    :param system: str
    :return: dict
    """
    entries = _matching_entries(stream, architecture, tag, system)
    for entry in sorted(
        entries, key=lambda entry: _sort_key(_run_date(entry)), reverse=True
    ):
        run = _read_run(entry)
        if run is not None:
            return run
    return {}


def streams():
    """
    Get available streams.
    """
    with open(_index_file(), "r") as f:
        test_result_index = json.load(f)
    return {tr["stream"] for tr in test_result_index}


def parser():
    description = """Add the test results from a given directory to the database."""
    parse = argparse.ArgumentParser(description=description)
    parse.add_argument(
        "directory", help="The directory containing all test result logs."
    )
    parse.add_argument(
        "--stream", help="The named stream this test suite belongs to.", required=True
    )
    parse.add_argument(
        "--tag",
        help="Optional string tags to refer to this test suite in the future.",
        dest="tags",
        default=[],
        action="append",
    )
    return parse


def main():
    import sys

    args = parser().parse_args()
    try:
        add(args.directory, stream=args.stream)
    except TestResultException as e:
        LOGGER.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
