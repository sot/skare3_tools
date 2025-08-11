#!/usr/bin/env python

import argparse
import datetime
import json
from pathlib import Path

from skare3_tools import packages
from skare3_tools import test_results as tr
from skare3_tools.dashboard import get_template

package_name_map = packages.get_package_list()


def dashboard(config=None, render=True):
    if config is None:
        config = {"static_dir": "static"}

    exclude = ["skare"]

    info = packages.get_repositories_info()
    test_results = tr.get_latest(stream="ska3-masters")

    repo2name = {p["repository"]: p["name"] for p in package_name_map}

    info["packages"] = sorted(
        [p for p in info["packages"] if p["name"] not in exclude],
        key=lambda p: p["name"],
    )
    for p in info["packages"]:
        for pr in p["pull_requests"]:
            if pr["last_commit_date"] is None:
                pr["last_commit_date"] = ""
            else:
                pr["last_commit_date"] = (
                    datetime.datetime.strptime(
                        pr["last_commit_date"], "%Y-%m-%dT%H:%M:%SZ"
                    )
                    .date()
                    .isoformat()
                )
        p["test_version"] = ""
        p["test_status"] = ""
        repo = "{owner}/{name}".format(**p)
        if repo in repo2name:
            package_tests = []
            if "test_suites" in test_results:
                package_tests = [
                    ts
                    for ts in test_results["test_suites"]
                    if ts["package"] == repo2name[repo]
                ]
            if package_tests:
                status = [
                    tc["status"] for ts in package_tests for tc in ts["test_cases"]
                ]
                p["test_version"] = package_tests[0]["properties"]["package_version"]
                if [s for s in status if s == "fail"]:
                    p["test_status"] = "FAIL"
                elif len(status) == len([s for s in status if s == "skipped"]):
                    p["test_status"] = "SKIP"
                else:
                    p["test_status"] = "PASS"

    if not render:
        return info

    template = get_template("dashboard.html")
    return template.render(title="Skare3 Packages", info=info, config=config)


def get_parser():
    parser = argparse.ArgumentParser(
        description="Produce a single html page with package information"
    )
    parser.add_argument(
        "-o",
        metavar="FILENAME",
        help="Output file (default: index.html)",
        default="index.html",
        type=Path,
    )
    return parser


def main():
    args = get_parser().parse_args()
    with open(args.o, "w") as out:
        if args.o.suffix == ".json":
            json.dump(dashboard(render=False), out)
        else:
            out.write(dashboard())


if __name__ == "__main__":
    main()
