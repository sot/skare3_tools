#!/usr/bin/env python3
"""
This module includes a very primitive database of test
results. It is assumed that test results are grouped in "test suites", which are just a group of
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
import os
import shutil
import tempfile
import logging

from pathlib import Path
from cxotime import CxoTime, units as u
from tqdm import tqdm
from skare3_tools.config import CONFIG


class TestResultException(Exception):
    pass


SKARE3_TEST_DATA = Path(CONFIG["data_dir"]).absolute() / "test_logs"
INDEX_FILE = SKARE3_TEST_DATA / "index.json"

if not SKARE3_TEST_DATA.exists():
    SKARE3_TEST_DATA.mkdir(parents=True)

if not INDEX_FILE.exists():
    with open(INDEX_FILE, "w") as f:
        f.write("[]")
    del f


LOGGER = logging.getLogger("skare3_tools")


def remove(uid=None, directory=None, uids=(), directories=()):
    with open(INDEX_FILE, "r") as fh:
        test_result_index = json.load(fh)

    uids = list(uids)
    if uid and uid not in uids:
        uids += [uid]

    directories = [SKARE3_TEST_DATA / directory for directory in directories]
    if directory and directory not in directories:
        directories += [SKARE3_TEST_DATA / directory]

    # make sure all directories are absolute and within the data tree
    for directory in directories:
        if SKARE3_TEST_DATA not in directory.resolve().parents:
            LOGGER.warning(f"warning: {directory} not in SKARE3_DASH_DATA. Ignoring")
    directories = [
        directory for directory in directories if SKARE3_TEST_DATA in directory.resolve().parents
    ]

    # make a list of everything that will be removed
    rm = [
        tr for tr in test_result_index
        if tr["uid"] in uids
        or SKARE3_TEST_DATA / tr["destination"] in directories
    ]

    for tr in rm:
        test_result_index.remove(tr)
        shutil.rmtree(SKARE3_TEST_DATA / tr["destination"])

    for directory in directories:
        if directory.exists():
            LOGGER.warning(
                f"The directory {directory} is still there."
                "This does not happen unless the directory is already not in the index,"
                "in which case it is safe to remove it by hand."
                )

    with open(INDEX_FILE, "w") as fh:
        json.dump(test_result_index, fh, indent=2)


def remove_older_than(days):
    with open(INDEX_FILE, "r") as fh:
        test_result_index = json.load(fh)

    for tr in test_result_index:
        all_test_log = SKARE3_TEST_DATA / tr["destination"] / "all_tests.json"
        with open(all_test_log) as fh:
            test_suites = json.load(fh)
            date = CxoTime(test_suites["run_info"]["date"])
            rm = []
            if date < CxoTime() - days * u.day:
                rm.append(tr["uid"])
            remove(uids=rm)


def add(directory, stream, tags=(), properties={}):
    """
    Add the test results from a given directory to the database.

    :param directory:
    :param stream: str
    :param tags: list
    :param properties: dict.
        Other properties to store about this test suite.
    :return:
    """
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

    with open(INDEX_FILE, "r") as f:
        test_result_index = json.load(f)

    if uid in [r["uid"] for r in test_result_index]:
        raise TestResultException("These test results already exist")

    all_test_log = directory / "all_tests.json"
    with open(all_test_log) as f:
        test_suites = json.load(f)

    date = test_suites["run_info"]["date"]
    destination = "{stream}_{date}_{uid}".format(stream=stream, date=date, uid=uid)
    abs_destination = SKARE3_TEST_DATA / destination
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
        ts["n_skip"] = len([tc for tc in ts["test_cases"] if "skipped" in tc])
        ts["n_fail"] = len([tc for tc in ts["test_cases"] if "fail" in tc])
        ts["n_pass"] = len([tc for tc in ts["test_cases"] if "pass" in tc])
        if ts["n_skip"] == len(ts["test_cases"]):
            ts["status"] = "skipped"
        elif ts["n_fail"] > 0:
            ts["status"] = "fail"
        else:
            ts["status"] = "pass"

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
            k: sorted(set([ts["properties"][k] for ts in test_suites["test_suites"]]))
            for k in ["architecture", "hostname", "system", "platform"]
        }
    )
    test_result_index.append(result)

    # copying to a temporary directory first, to make sure there are no surprises
    with tempfile.TemporaryDirectory() as tmpdirname:
        tmp_destination = Path(tmpdirname) / destination
        shutil.copytree(
            directory,
            tmp_destination,
            ignore=_ignore_unreadable
        )
        shutil.copy(
            all_test_log,
            tmp_destination / (all_test_log.name + '.orig')
        )
        with open(tmp_destination / all_test_log.name , "w") as f:
            json.dump(test_suites, f, indent=2)

        # after that succeeded, copy to the final destination (which does not exist yet)
        shutil.copytree(
            tmp_destination,
            abs_destination,
        )

    with open(INDEX_FILE, "w") as f:
        json.dump(test_result_index, f, indent=2)


def _ignore_unreadable(src, names):
    # this is used in shutil.copytree to ignore files that are not readable due to permissions
    return [name for name in names if not os.access(os.path.join(src, name), os.R_OK)]


def get(stream=None, architecture=None, tag=None, system=None):
    """
    Get all the test results for the given stream, architecture, tag and system sorted by date.

    :param stream: str
    :param architecture: str
    :param tag: str
    :param system: str
    :return: list
    """
    with open(INDEX_FILE, "r") as f:
        test_result_index = json.load(f)

    result = []
    for tr in test_result_index:
        if (
            (stream and stream not in tr["stream"])
            or (architecture and architecture not in tr["architecture"])
            or (tag and tag not in tr["tag"])
            or (system and system not in tr["system"])
        ):
            continue
        directory = tr["destination"]
        all_test_log = SKARE3_TEST_DATA / directory / "all_tests.json"
        with open(all_test_log) as f:
            test_suites = json.load(f)
            if "run_info" not in test_suites:
                test_suites["run_info"] = {}
            test_suites["run_info"] = {**tr, **test_suites["run_info"]}
            result.append(test_suites)
    return sorted(result, key=lambda r: r["run_info"]["date"])


def get_latest(stream=None, architecture=None, tag=None, system=None):
    """
    Get the latest test results for the given stream, architecture, tag and system.

    :param stream: str
    :param architecture: str
    :param tag: str
    :param system: str
    :return: dict
    """
    test_results = get(stream=stream, architecture=architecture, tag=tag, system=system)
    test_results = test_results[-1] if len(test_results) else {}
    return test_results


def streams():
    """
    Get available streams.
    """
    with open(INDEX_FILE, "r") as f:
        test_result_index = json.load(f)
    return set([tr["stream"] for tr in test_result_index])


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
        LOGGER.error("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
