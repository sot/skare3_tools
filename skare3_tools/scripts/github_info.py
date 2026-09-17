"""
``skare3-github-info``: write the status of all packages to a JSON file.

This queries Github and the conda channels directly, so it needs a token and
takes minutes. The data store holds the same aggregate, rebuilt hourly and
readable without a token: see :mod:`skare3_tools.packages.store` and
:class:`skare3_tools.packages.DataClient`.
"""

import argparse
import json

from skare3_tools import github, packages


def get_parser():
    parser = argparse.ArgumentParser(
        description="Query Github for the status of all packages."
    )
    parser.add_argument(
        "-o",
        default="repository_info.json",
        help="Output file (default=repository_info.json)",
    )
    parser.add_argument(
        "--token", help="Github token, or name of file that contains token"
    )
    return parser


def main():
    args = get_parser().parse_args()

    github.init(token=args.token)

    info = packages.get_repositories_info(update=True)
    if info:
        with open(args.o, "w") as f:
            json.dump(info, f, indent=2)


if __name__ == "__main__":
    main()
