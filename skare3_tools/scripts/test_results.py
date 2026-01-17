#!/usr/bin/env python3
"""
Deprecated Script: Gather test results from testr's log file.
"""

import argparse
import importlib
import json
import re
from pathlib import Path


def test_results(directory):
    filename = directory / "test.log"
    with open(filename) as f:
        for line in f:
            if re.match(r"\*\*\*\s+Package\s+Script\s+Status\s+\*\*\*", line):
                break
        results = [
            line.split()[1:-1]
            for line in f
            if re.search("fail", line.lower()) or re.search("pass", line.lower())
        ]

        result_dict = {k[0]: {"tests": {}} for k in results}
        for k in results:
            try:
                module = importlib.import_module(k[0])
                version = module.__version__
            except Exception:
                version = ""
            result_dict[k[0]]["tests"][k[1]] = k[2].upper()
            res = result_dict[k[0]]["tests"].values()
            result_dict[k[0]]["pass"] = not sum([r == "FAIL" for r in res])
            result_dict[k[0]]["version"] = version

            test_results = {
                "log_directory": directory.name,
                "results": result_dict,
            }
    return test_results


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument(
        "directory",
        help="Directory containing all test results."
        "It must contain a file named test.log",
        type=Path,
    )
    parse.add_argument(
        "-o",
        help="Output file name (default: test_results.json)",
        default="test_results.json",
        type=Path,
    )
    return parse


def main():
    args = parser().parse_args()
    with open(args.o, "w") as f:
        json.dump(test_results(args.directory), f, indent=2)


if __name__ == "__main__":
    main()
