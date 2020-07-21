#!/usr/bin/env python3
"""
Check the environment and conda configuration files to determine which packages to build, if any.
It also does a sanity check, checking whether the release is from a branch with the same name,
and whether the release and tag exist.
"""

import argparse
import sys
import os
import re
import yaml
import glob
import logging
import git
from skare3_tools import github

logging.basicConfig(level='INFO')


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('--version', required=True, help='Target version to build')
    parse.add_argument('--skare3-path', default='.', help='skare3 directory')
    parse.add_argument('--repository', default='sot/skare3')
    parse.add_argument('--token', '-t', help='Github token, or name of file that contains token')
    parse.add_argument('--no-check', dest='ci_sanity_check', action='store_false',
                       default=True, help='Checks for CI')
    return parse


def main():
    arg_parser = parser()
    args = arg_parser.parse_args()
    args.skare3_path = os.path.abspath(args.skare3_path)

    git_repo = None
    try:
        git_repo = git.Repo(args.skare3_path)
    except git.NoSuchPathError:
        logging.error(f'--skare3-path points to non-existent directory "{args.skare3_path}".')
    except git.InvalidGitRepositoryError:
        logging.error(f'--skare3-path points to an invalid git repo "{args.skare3_path}".')
    if git_repo is None:
        sys.exit(2)

    tag_name = args.version.strip('/').split('/')[-1]  # versions can be git refs like refs/tags/V2
    m = re.match('(?P<version>[0-9]+(.[0-9]+(.[0-9]+)?)?)(rc(?P<rc>[0-9]+))?', tag_name)
    version = m.groupdict()['version']

    # some sanity checks
    fail = []
    logging.info(f'Sanity check for release {tag_name}, target version {version}')

    github.init(token=args.token)
    repository = github.Repository(args.repository)

    tag = repository.tags(name=tag_name)
    release = repository.releases(tag_name=tag_name)
    pulls = repository.pull_requests(state='open', head=f'sot:{version}')
    if args.ci_sanity_check:

        """
        The following checks that:
        - release exists
        - release tag exists
        - release tag is on branch named after this release
        - there is a PR named after this release
        - if GITHUB_SHA is defined, it must be the release commit.
        """
        if 'response' in release and not release['response']['ok']:
            fail.append(f'Release {tag_name} does not exist')
        elif release['target_commitish'] != version:
            fail.append(f'Release {tag_name} not on branch {version}')
        if 'response' in tag and not tag['response']['ok']:
            fail.append(f'Tag {tag_name} does not exist')
        # are these always true? release from master? release without open PR?
        if 'response' in pulls and not pulls['response']['ok']:
            fail.append(f'There is no pull request from sot:{version}')
        # when workflow triggered by release, GITHUB_SHA must have the release commit sha
        if 'GITHUB_SHA' in os.environ:
            if os.environ['GITHUB_SHA'] != tag['object']['sha']:
                fail.append(f"Tag {tag_name} sha differs from sha in GITHUB_SHA: "
                            f"{tag['object']['sha']} != {os.environ['GITHUB_SHA']}")
        elif git_repo.active_branch.name != version:
            fail.append(f'Current branch is different from release branch '
                        f'({git_repo.active_branch.name} != {version})')
        for f in fail:
            logging.warning(f)
        if fail:
            sys.exit(1)

    # checking package versions
    files = glob.glob(os.path.join(args.skare3_path, 'pkg_defs', 'ska3-*', 'meta.yaml'))
    packages = []
    for filename in files:
        with open(filename) as f:
            data = yaml.load(f)
            if str(version) == str(data['package']['version']):
                packages.append(data['package']['name'])

    packages = ' '.join(packages)

    print(f'::set-output name=prerelease::{release["prerelease"]}')
    print(f'::set-output name=packages::{packages}')


if __name__ == '__main__':
    main()
