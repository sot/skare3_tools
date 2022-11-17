#!/usr/bin/env python3
"""
Deprecated Script: Gather test results from testr's log file.
"""

import argparse
import importlib
import json
import os
import re


def test_results(directory):
    filename = os.path.join(directory, "test.log")
    with open(filename) as f:
        for l in f:
            if re.match("\*\*\*\s+Package\s+Script\s+Status\s+\*\*\*", l):
                break
        results = []
        for l in f:
            if re.search("fail", l.lower()) or re.search("pass", l.lower()):
                results.append(l.split()[1:-1])
        result_dict = {k[0]: {"tests": {}} for k in results}
        for k in results:
            try:
                module = importlib.import_module(k[0])
                version = module.__version__
            except:
                version = ""
            result_dict[k[0]]["tests"][k[1]] = k[2].upper()
            res = result_dict[k[0]]["tests"].values()
            result_dict[k[0]]["pass"] = not sum([r == "FAIL" for r in res])
            result_dict[k[0]]["version"] = version

            test_results = {
                "log_directory": os.path.basename(directory),
                "results": result_dict,
            }
    return test_results


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument(
        "directory",
        help="Directory containing all test results."
        "It must contain a file named test.log",
    )
    parse.add_argument(
        "-o",
        help="Output file name (default: test_results.json)",
        default="test_results.json",
    )
    return parse


def main():
    args = parser().parse_args()
    with open(args.o, "w") as f:
        json.dump(test_results(args.directory), f, indent=2)


if __name__ == "__main__":
    main()
