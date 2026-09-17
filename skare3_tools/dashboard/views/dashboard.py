#!/usr/bin/env python
"""
Render the package dashboard from the data store.

This view only reads (through :class:`~skare3_tools.packages.DataClient`)
and renders: producing the data is ``skare3-refresh``'s job. Writing the
JSON output is therefore just a copy of the store aggregate.
"""

import argparse
import copy
import datetime
import json
from pathlib import Path

from skare3_tools.dashboard import get_template
from skare3_tools.packages import DataClient


def dashboard(config=None, render=True, client=None):
    if config is None:
        config = {"static_dir": "static"}
    if client is None:
        client = DataClient()

    info = client.packages()
    if not render:
        return info

    # cosmetic touch-up for the HTML table only: PR dates trimmed to days
    info = copy.deepcopy(info)
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
    parser.add_argument(
        "--source",
        choices=["auto", "local", "http", "github"],
        default="auto",
        help="Where to read the data from (default: auto)",
    )
    parser.add_argument(
        "--data-dir", type=Path, help="Local store directory (with --source=local)"
    )
    return parser


def main():
    args = get_parser().parse_args()
    client = DataClient(source=args.source, data_dir=args.data_dir)
    with open(args.o, "w") as out:
        if args.o.suffix == ".json":
            json.dump(dashboard(render=False, client=client), out)
        else:
            out.write(dashboard(client=client))


if __name__ == "__main__":
    main()
