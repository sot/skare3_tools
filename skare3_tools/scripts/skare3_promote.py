#!/usr/bin/env python
"""
Promote ska3 meta-packages from a list of channels to one target channel.

"Promotion" usually means copying conda package files from the source
channels to the target channel. The channels are expected to be within
the same directory, which is specified by the `ska3-conda` argument.

The meta-packages to be promoted must be defined in skare3. This script
reads the metapackage's meta.yaml requirements in skare3, finds the
corresponding packages in the source channels, and copies/moves them to the
target channel.
"""
import conda_build.metadata
import yaml
import pathlib
import sys
import re
import git
import tempfile
import argparse
import logging
import subprocess
import shutil
import logging


SKARE3_URL = 'git@github.com:sot/skare3.git'
SKA3_CONDA = '/proj/sot/ska/www/ASPECT_ICXC/ska3-conda'
TO_CHANNEL = 'flight'
FROM_CHANNELS = ['test', 'masters']
PLATFORM_OPTIONS = {'linux-64': {'linux': True, 'linux64': True},
                    'osx-64': {'osx': True, 'osx64': True},
                    'win-64': {'win': True, 'win64': True}}
SECTIONS = ['run']


def _files_to_copy(package,
                   platform,
                   ska3_conda,
                   to_channel,
                   from_channels):
    """
    Returns None if no files need to be copied, and empty list if they need to be copied, but they
    are not in from_channels.

    :param package:
    :param platform:
    :param ska3_conda:
    :param to_channel:
    :param from_channels:
    :return:
    """
    if not package['version']:
        # should not promote a package with no version
        return
    pkg_files = None
    pkg = f'{package["name"]}-{package["version"]}'
    dest_file = []
    from_file = []
    for arch in ['noarch', platform]:
        dest_file += list((ska3_conda / to_channel / arch).glob(f'{pkg}-*'))
        for from_channel in from_channels:
            from_file += list((ska3_conda / from_channel / arch).glob(f'{pkg}-*'))
    if not dest_file:
        pkg_files = []
        for file in from_file:
            p = {
                'pkg': pkg,
                'from': file,
                'to': ska3_conda / to_channel / file.relative_to(file.parents[1])
            }
            p.update(package)
            pkg_files.append(p)
    return pkg_files


def promote(package,args, platforms=None):
    if platforms is None:
        platforms = PLATFORM_OPTIONS

    m = re.search('(?P<name>\S+)(\s+)?==(\s+)?(?P<version>\S+)', package)
    if not m:
        raise Exception(f'Could not parse package name/version: {package}')
    package = m.groupdict()

    skare3_repo = git.Repo(args.skare3)
    skare3_repo.remotes.origin.fetch('--tags')
    try:
        skare3_repo.git.checkout(package['version'])
    except:
        logging.error(f"skare3 has no '{package['version']}' tag")
        return

    with open(args.skare3 / 'pkg_defs' / package['name'] / 'meta.yaml') as fh:
        meta = fh.read()

    pkg_files = []
    package_names = []
    fail = False
    for platform in platforms:
        data = conda_build.metadata.select_lines(meta, platforms[platform], {})
        data = yaml.load(data, Loader=yaml.BaseLoader)

        pkgs = _files_to_copy(package, platform, args.ska3_conda, args.to_channel, args.from_channels)
        # this might not be obvious...
        # if the list is empty, it means the package is not in the 'from' locations
        # and is not in the 'to' location either. Since this is a top-level pkg,
        # it could just be that the package should not be there for this platform
        # (e.g. ska3-perl on windows), so we do not try to go to the requirements
        # if this had been a requirement, then we would show an empty list, meaning it
        # was not found.
        if pkgs == []:
            logging.warning(f'package {package["name"]}=={package["version"]} not found for platform {platform}.')
            continue

        if pkgs is not None:
            package_names += [package['name']]
            pkg_files += pkgs
        else:
            logging.debug(f'package {package["name"]} is already promoted.')

        for section in SECTIONS:
            if section not in data['requirements']:
                continue
            for requirement in data['requirements'][section]:
                m = re.search('(?P<name>\S+)(\s+)?(==(\s+)?(?P<version>\S+))?', requirement)
                if m:
                    requirement = m.groupdict()

                    pkgs = _files_to_copy(requirement, platform, args.ska3_conda, args.to_channel, args.from_channels)
                    if pkgs is not None:
                        if requirement['name'] not in package_names:
                            package_names.append(requirement['name'])
                        pkg_files += pkgs
                        if not pkgs:
                            logging.warning(f"package {requirement['name']}=={requirement['version']} was not found")
                else:
                    logging.error(f'Could not parse requirement: "{requirement}"')
                    fail = True

    if fail:
        logging.error('Failed assembling package list (see errors above).')

    package_names = sorted(set(package_names))

    pkg_files_ = []
    for p in pkg_files:
        if p not in pkg_files_:
            pkg_files_.append(p)
    pkg_files = pkg_files_
    pkg_files = {name: [p for p in pkg_files if p['name'] == name] for name in package_names}

    row = '| {package:30s} | {noarch:24s} {noarch-src:7s} | {linux-64:24s} {linux-64-src:7s} | {osx-64:24s} {osx-64-src:7s} | {win-64:24s} {win-64-src:7s} |'
    div = {"package": "", "noarch": "", "linux-64": "", "osx-64": "", "win-64": ""}
    div.update({k: "" for k in ['noarch-src', 'linux-64-src', 'osx-64-src', 'win-64-src']})
    div = row.format(**div).replace(' ', '-').replace('|', '+')
    header = {"package": "package name", "noarch": "noarch", "linux-64": "linux-64", "osx-64": "osx-64", "win-64": "win-64"}
    header.update({k: "" for k in ['noarch-src', 'linux-64-src', 'osx-64-src', 'win-64-src']})
    header = row.format(**header)
    logging.info(div)
    logging.info(header)
    logging.info(div)
    for name in package_names:
        versions = {platform: '---' for platform in
                    ['noarch', 'linux-64', 'osx-64', 'win-64', 'noarch-src', 'linux-64-src', 'osx-64-src', 'win-64-src']}
        versions['package'] = name
        for pkg in pkg_files[name]:
            if pkg["version"] is None:
                pkg["version"] = "???"
            assert pkg["from"].name == pkg["to"].name
            assert pkg["from"].exists()
            versions[str(pkg["from"].parent.name)] = pkg["version"]
            versions[str(pkg["from"].parent.name) + '-src'] = str(pkg["from"].parent.parent.name)
        logging.info(row.format(**versions))
    logging.info(div)

    if not args.dry_run:
        for name in pkg_files:
            for pkg in pkg_files[name]:
                if not pkg["to"].parent.exists():
                    pkg["to"].parent.mkdir(parents=True)
                if args.move:
                    pkg["from"].replace(pkg["to"])
                else:
                    shutil.copy2(pkg["from"], pkg["to"])


def parser():
    usage = "%(prog)s [-h] [--ska3-conda SKA3_CONDA] [--from FROM_CHANNEL [--from FROM_CHANNEL ...] ] [--to TO_CHANNEL] [--dry-run] [--move] [--skare3-local-copy SKARE3] [--log-level {error,warning,info,debug}] [-v] <package name>==<version> [<package name>==<version> ...]"
    parse = argparse.ArgumentParser(description=__doc__, usage=usage)
    parse.add_argument('package', nargs='+', metavar='<package name>==<version>')
    parse.add_argument('--ska3-conda', help="ska3-conda directory containing source and target channels", default=SKA3_CONDA)
    parse.add_argument('--from', help="source channel", dest='from_channels', action='append')
    parse.add_argument('--to', help="target channel", dest='to_channel')
    parse.add_argument('--dry-run', help="do not copy/move and do not index target conda channel", action='store_true', default=False)
    parse.add_argument('--move', help="move packages instead of copying", action='store_true', default=False)
    parse.add_argument('--skare3-local-copy', help='path to the local copy of the skare3 repo (on a tempdir by default)', dest='skare3')
    parse.add_argument('--log-level',
                       help="verbosity level (error, warning, info, debug)",
                       choices=['error', 'warning', 'info', 'debug'],
                       default='info')
    parse.add_argument('-v',
                       help="Debug verbosity",
                       dest='log_level', action='store_const', const='debug')
    return parse


def main():
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)

        args = parser().parse_args()
        logging.basicConfig(level=args.log_level.upper(), format='%(message)s')

        args.ska3_conda = pathlib.Path(args.ska3_conda).expanduser()
        if args.to_channel is None:
            args.to_channel = TO_CHANNEL
        if args.from_channels is None:
            args.from_channels = FROM_CHANNELS
        if args.skare3 is None:
            args.skare3 = td / 'skare'
        args.skare3 = pathlib.Path(args.skare3)
        if not args.ska3_conda.exists():
            logging.error(f'"{args.ska3_conda}" does not exist.')
            sys.exit(1)

        if not args.skare3.exists():
            repo = git.Repo.clone_from(SKARE3_URL, args.skare3)
        else:
            repo = git.Repo(args.skare3)

        for package in args.package:
            logging.info(package)
            logging.info('='*len(package))
            promote(package, args)

    if not args.dry_run:
        subprocess.call(['conda', 'index', str(args.ska3_conda / args.to_channel)])


if __name__ == '__main__':
    main()
