"""
Publish a testr log directory to the web archive.

Replaces the copy step of copy_logs.sh: copy the latest testr logs into a
timestamped directory under the archive and point the ``last`` symlink at it.
The dashboards link to these logs (their --log-dir URLs serve the archive).
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path


def publish_logs(source, archive):
    """
    Copy ``source`` to ``archive/<timestamp>`` and update ``archive/last``.

    :param source: log directory to publish (may be a symlink, e.g. logs/last).
    :param archive: directory holding the timestamped copies and the ``last``
        symlink.
    :return: the timestamped destination directory.
    """
    source = Path(source).resolve()
    archive = Path(archive)
    dest = archive / datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    shutil.copytree(source, dest)
    last = archive / "last"
    if last.is_symlink() or last.exists():
        last.unlink()
    last.symlink_to(dest)
    return dest


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Log directory to publish")
    parser.add_argument("archive", type=Path, help="Web archive directory")
    return parser


def main():
    args = get_parser().parse_args()
    if not args.source.is_dir():
        sys.exit(f"log directory does not exist: {args.source}")
    if not args.archive.is_dir():
        sys.exit(f"archive directory does not exist: {args.archive}")
    dest = publish_logs(args.source, args.archive)
    print(dest)


if __name__ == "__main__":
    main()
