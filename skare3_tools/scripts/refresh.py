"""
``skare3-refresh``: bring the package-data store up to date.

The work is in :mod:`skare3_tools.packages.refresh`; this is only the
command-line entry point. ``--data-dir`` runs against a scratch store instead
of the configured one, ``--full`` refetches every repository instead of the
changed ones, and ``--ingest-tests`` adds a testr output directory to the
test-results store before refreshing.

A run that could not fetch everything it wanted still writes what it has and
exits non-zero, listing what failed.
"""

import argparse
import logging
import sys
from pathlib import Path

from skare3_tools import test_results
from skare3_tools.packages import refresh, store

# the producer's own logger, so -v raises the verbosity of the refresh itself
logger = logging.getLogger("skare3.refresh")


def get_parser():
    parser = argparse.ArgumentParser(
        description="Bring the package-data store up to date."
    )
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
    # verbosity applies to this logger only: at DEBUG level the github
    # wrapper logs request headers, including the authorization token
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    if args.ingest_tests:
        test_results.add(str(args.ingest_tests), stream=args.stream)
    try:
        summary = refresh.refresh(
            data_dir=args.data_dir, full=args.full, stream=args.stream
        )
    except (refresh.RefreshError, store.StoreLockedError) as exc:
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
