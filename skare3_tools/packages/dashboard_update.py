"""
Publish the data store for HTTP readers.

``skare3-dashboard-update`` is the hourly production entry point: refresh the
store, then copy the published subset into the public dashboard directory —
``packages.json`` and ``test_results.json`` (fetched by the React dashboard),
``repository_status.json`` and the ``repos/`` tree (the DataClient HTTP tier).

The store's ``manifest.json`` and ``meta/`` are never published: the manifest
name collides with the React app's own ``manifest.json`` at the public root
(and the HTTP tier does not read it), and ``meta/`` is producer bookkeeping.

Files are copied via a temp name + ``os.replace`` so HTTP readers see the old
or the new content, never a partial file.
"""

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

from skare3_tools.packages import refresh, store

logger = logging.getLogger("skare3.dashboard_update")

PUBLISHED_FILES = ("packages.json", "test_results.json", "repository_status.json")


def _atomic_copy(src, dest):
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)


def _mirror_repos(src, dest):
    """Make dest an exact copy of the repos/ tree (copy all, drop leftovers)."""
    wanted = set()
    for path in src.rglob("*.json"):
        relative = path.relative_to(src)
        wanted.add(relative)
        (dest / relative).parent.mkdir(parents=True, exist_ok=True)
        _atomic_copy(path, dest / relative)
    for path in list(dest.rglob("*.json")):
        if path.relative_to(dest) not in wanted:
            path.unlink()


def publish(publish_dir, data_dir=None):
    """
    Copy the published subset of the store into ``publish_dir``.

    :param publish_dir: public directory served over HTTP.
    :param data_dir: store directory (default: the configured store root).
    """
    data_dir = Path(data_dir) if data_dir else store.store_dir()
    publish_dir = Path(publish_dir)
    for name in PUBLISHED_FILES:
        _atomic_copy(data_dir / name, publish_dir / name)
    _mirror_repos(data_dir / "repos", publish_dir / "repos")
    logger.info("published store to %s", publish_dir)


def get_parser():
    parser = argparse.ArgumentParser(
        description="Refresh the data store and publish it (the hourly dashboard job)."
    )
    parser.add_argument(
        "--publish-dir",
        metavar="DIR",
        type=Path,
        required=True,
        help="Public directory served over HTTP",
    )
    parser.add_argument(
        "--data-dir",
        metavar="DIR",
        type=Path,
        help="Store directory (default: the configured store root)",
    )
    parser.add_argument(
        "--stream",
        default="ska3-masters",
        help="Test-results stream baked into the aggregate",
    )
    return parser


def main():
    args = get_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        summary = refresh.refresh(data_dir=args.data_dir, stream=args.stream)
    except (refresh.RefreshError, store.StoreLockedError) as exc:
        sys.exit(f"refresh failed: {exc}")
    # per-repo fetch failures keep the previous good data in the store:
    # publish what we have, then exit non-zero so the scheduler alerts
    publish(args.publish_dir, data_dir=args.data_dir)
    if summary["failures"]:
        sys.exit(
            "failed to fetch:\n"
            + "\n".join(f"  {k}: {v}" for k, v in summary["failures"].items())
        )


if __name__ == "__main__":
    main()
