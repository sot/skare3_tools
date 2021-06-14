"""
    Gets the list of installed packages and searches for them in cache directories,
    copying them into a destination directory. Optionally exclude or only include some channels.
"""

import os
import subprocess
import json
from pathlib import Path
import shutil
import argparse
import logging
import re


logger = logging.getLogger('skare3_tools.conda')


def gather_env_pkgs(directory, pkgs_dir=None, include_channels=None, exclude_channels=()):
    """
    Gets the list of installed packages and searches for them in cache directories,
    copying them into a destination directory.

    Optionally exclude or only include some channels.
    """
    directory = Path(directory)
    if pkgs_dir is None:
        pkgs_dirs = Path(os.environ['CONDA_PREFIX']).parts
        pkgs_dirs = [Path(*pkgs_dirs[:i + 1]) for i in range(len(pkgs_dirs))]
        pkgs_dirs = [p for p in pkgs_dirs if (p / 'pkgs').exists()]

        if 'CONDA_PKGS_DIR' in os.environ:
            pkgs_dirs += [Path(os.environ['CONDA_PKGS_DIR'])]

        pkgs_dirs = pkgs_dirs[::-1]
    else:
        pkgs_dirs = [pkgs_dir]
    all_pkgs = json.loads(subprocess.check_output(['conda', 'list', '--no-pip', '--json']).decode())
    pkgs = []
    for p in all_pkgs:
        logger.debug(f'Package: {p}')
        match = []
        if exclude_channels:
            match = [re.search(c, p['channel']) for c in exclude_channels]
            match = [bool(m) and m.span()[0] == 0 and m.span()[1] == len(p['channel'])
                     for m in match]
            if sum(match):
                logger.debug('  in excluded channel')
                continue
        if include_channels and ['channel'] not in include_channels:
            logger.debug('  not in an included channel')
            continue
        logger.debug('  included')
        pkgs.append(p)

    logger.info('Copying packages')
    for pkg in pkgs:
        name = ''
        for pkgs_dir in pkgs_dirs:
            if (pkgs_dir / f'{pkg["dist_name"]}.conda').exists():
                name = pkgs_dir / f'{pkg["dist_name"]}.conda'
            elif (pkgs_dir / f'{pkg["dist_name"]}.tar.bz2').exists():
                name = pkgs_dir / f'{pkg["dist_name"]}.tar.bz2'
            if name:
                (directory / pkg["platform"]).mkdir(parents=True, exist_ok=True)
                logger.info(f'  - {pkg["dist_name"]}: {name}')
                shutil.copy(name, directory / pkg["platform"])
                break
        if not name:
            logger.info(f'  - {pkg["dist_name"]} not found')


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True,
                        help='Destination directory where packages should be placed')
    parser.add_argument('--pkgs-dir',
                        help='Cache directory. The default is to look in the usual places')
    parser.add_argument('--include-channel', action='append', default=[],
                        help='Only include packages from these channels')
    parser.add_argument('--exclude-channel', action='append', default=[],
                        help='Do not include packages from these channels')
    parser.add_argument(
        '--log-level',
        help='logging level',
        choices=['debug', 'info', 'warning'],
        default='info'
    )
    return parser


def main():
    import pyyaks

    args = get_parser().parse_args()

    pyyaks.logger.get_logger(
        name='skare3_tools.conda',
        level=args.log_level.upper(),
        format="%(asctime)s %(message)s"
    )

    gather_env_pkgs(args.directory,
                    pkgs_dir=args.pkgs_dir,
                    exclude_channels=args.exclude_channel,
                    include_channels=args.include_channel)


if __name__ == '__main__':
    main()
