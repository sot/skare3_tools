import os
import subprocess
import json
from pathlib import Path
import shutil
import argparse
import logging
import re


logger = logging.getLogger("skare3_tools.conda")


def gather_env_pkgs(
    directory, pkgs_dir=None, include_channels=None, exclude_channels=()
):
    directory = Path(directory)
    if pkgs_dir is None:
        parts = []
        for part in Path(os.environ["CONDA_PREFIX"]).parts:
            if part == "envs":
                parts.append("pkgs")
                break
            else:
                parts.append(part)
        pkgs_dir = Path(*parts)
    all_pkgs = json.loads(
        subprocess.check_output(["conda", "list", "--no-pip", "--json"]).decode()
    )
    pkgs = []
    for p in all_pkgs:
        match = []
        if exclude_channels:
            match = [re.search(c, p["channel"]) for c in exclude_channels]
            match = [
                bool(m) and m.span()[0] == 0 and m.span()[1] == len(p["channel"])
                for m in match
            ]
            if sum(match):
                continue
        if include_channels and ["channel"] not in include_channels:
            continue
        pkgs.append(p)

    if pkgs and not directory.exists():
        directory.mkdir(parents=True)
    for pkg in pkgs:
        name = ""
        if (pkgs_dir / f'{pkg["dist_name"]}.conda').exists():
            name = pkgs_dir / f'{pkg["dist_name"]}.conda'
        elif (pkgs_dir / f'{pkg["dist_name"]}.tar.bz2').exists():
            name = pkgs_dir / f'{pkg["dist_name"]}.tar.bz2'
        if name:
            shutil.copy(name, directory)
        else:
            logger.debug(f'ignored {pkg["dist_name"]}')


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--pkgs-dir")
    parser.add_argument("--include-channel", action="append", default=[])
    parser.add_argument("--exclude-channel", action="append", default=[])
    return parser


def main():
    args = get_parser().parse_args()
    gather_env_pkgs(
        args.directory,
        pkgs_dir=args.pkgs_dir,
        exclude_channels=args.exclude_channel,
        include_channels=args.include_channel,
    )


if __name__ == "__main__":
    main()
