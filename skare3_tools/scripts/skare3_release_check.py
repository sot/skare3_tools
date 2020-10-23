#!/usr/bin/env python3
"""
Check the environment and conda configuration files to determine which packages to build, if any.
It also does a sanity check, checking consistency between release tag and branch. It is assumed that
the 'target' version (the version after all tests pass) is the name of the branch where the release
is made. This script checks the meta information of all ska3-* packages to see which ones have
version equal to the target version and adds those to a list of packages to build.

This script makes the following checks:

* the given tag exists and follows PEP 0440 format (https://www.python.org/dev/peps/pep-0440),
* there is an existing release with this tag,
* the tag's branch must be named '<release>' or '<release>-<label>',
* there exists a PR based on this branch,
* if tag_name contains an alpha/beta/candidate version, then release must be a pre-release,
* if tag_name contains a label, then release must be a pre-release,
* if GITHUB_SHA is defined, it must be the release commit.
  If not, the local copy of the skare3 repo must be in the tag branch.
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
    parse.add_argument('--skare3-path', default='.', help='local copy of the skare3 repo')
    parse.add_argument('--repository', default='sot/skare3', help='Github repository name')
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
        sys.exit(1)

    tag_name = args.version.strip('/').split('/')[-1]  # versions can be git refs like refs/tags/V2
    # regular expression (mostly) matching PEP-0440 version format
    fmt = '(?P<final_version>((?P<epoch>[0-9]+)!)?(?P<release>[0-9]+(.[0-9]+(.[0-9]+)?)?))' \
          '((a|b|rc)(?P<rc>[0-9]+))?(\+(?P<label>[a-zA-Z]+))?$'
    version_info = re.match(fmt, tag_name)
    if not version_info:
        logging.warning(f'Tag name must conform to PEP-440 format'
                        f' (https://www.python.org/dev/peps/pep-0440)')
        sys.exit(2)
    version_info = version_info.groupdict()

    allowed_names = [version_info['final_version']]
    if version_info['label']:
        allowed_names += [f'{version_info["final_version"]}+{version_info["label"]}']

    logging.info(f'Sanity check for release {tag_name}')

    github.init(token=args.token)
    repository = github.Repository(args.repository)

    tag = repository.tags(name=tag_name)
    release = repository.releases(tag_name=tag_name)

    # some sanity checks
    fail = []
    if args.ci_sanity_check:

        """
        The following checks that:
        - release exists
        - release tag exists
        - the branch where the tag was made must be in the allowed_names list
        - there is a PR based on this branch
        - the tag branch name must be the final_release version, or <final_version>-<label>
        - if tag_name contains an alpha/beta/candidate version, then release must be a pre-release
        - if tag_name contains a label, then release must be a pre-release
        - if GITHUB_SHA is defined, it must be the release commit.
          If not, the local copy of the skare3 repo must be in the tag branch.
        """
        try:
            if 'response' not in release or not release['response']['ok']:
                fail.append(f'Release {tag_name} does not exist')
            if 'response' not in tag or not tag['response']['ok']:
                fail.append(f'Tag {tag_name} does not exist')
            branch_name = ''
            if not fail:
                branch_name = release['target_commitish']
                pulls = repository.pull_requests(state='open', head=f'sot:{branch_name}')
                pulls = [p for p in pulls if p['title'] == branch_name]
                if branch_name not in allowed_names:
                    fail.append(f'Invalid branch name "{branch_name}" for release "{tag_name}". '
                                f'Allowed branch names for this tag are {", ".join(allowed_names)}')
                if not pulls:
                    fail.append(f'There is no pull request from sot:{branch_name}')
                if version_info['rc'] is not None and not release["prerelease"]:
                    fail.append(f'Release {tag_name} is marked as a candidate, '
                                f'but the release is not a prerelease')
                if version_info['label'] is not None and not release["prerelease"]:
                    fail.append(f'Release {tag_name} has label {version_info["label"]}, '
                                f'but the release is not a prerelease')
            # when workflow triggered by release, GITHUB_SHA must have the release commit sha
            if 'GITHUB_SHA' in os.environ:
                if os.environ['GITHUB_SHA'] != tag['object']['sha']:
                    fail.append(f"Tag {tag_name} sha differs from sha in GITHUB_SHA: "
                                f"{tag['object']['sha']} != {os.environ['GITHUB_SHA']}")
            elif git_repo.active_branch.name != branch_name:
                fail.append(f'Current branch is different from release branch '
                            f'("{git_repo.active_branch.name}" != "{branch_name}")')
        except Exception as e:
            exc_type = sys.exc_info()[0].__name__
            fail.append(f'Unexpected error ({exc_type}): {e}')
        for f in fail:
            logging.warning(f)
        if fail:
            sys.exit(3)

    # at this point, branch_name must be set, and it is taken to be the target version
    logging.info(f'Target version {branch_name}')
    # checking package versions
    # whenever a version equals `branch_name`, replace it by the full version.
    files = glob.glob(os.path.join(args.skare3_path, 'pkg_defs', 'ska3-*', 'meta.yaml'))
    packages = []
    for filename in files:
        with open(filename) as f:
            data = yaml.load(f, Loader=yaml.SafeLoader)
            if str(branch_name) == str(data['package']['version']):
                packages.append(data['package']['name'])

    packages = ' '.join(packages)

    print(f'prerelease: {release["prerelease"]}')
    print(f'packages: {packages}')
    print(f'overwrite_flag: --skare3-overwrite-version {branch_name}:{tag_name}')
    # this kind of output defines variables 'prerelease' and 'packages' within the workflow.
    print(f'::set-output name=prerelease::{release["prerelease"]}')
    print(f'::set-output name=packages::{packages}')
    print(f'::set-output name=overwrite_flag::whatever')


if __name__ == '__main__':
    main()
