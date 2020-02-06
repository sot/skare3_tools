#!/usr/bin/env python3
"""
Create a pull request
"""

import sys
import argparse
from skare3_tools import github


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('--repository',
                       required=True, help='repository name. Example: sot/chandra_aca')
    parse.add_argument('--pull-number', help='pull number')
    parse.add_argument('--head', help='branch you are merging from')
    parse.add_argument('--base', help='branch you are merging to')
    parse.add_argument('--commit-title')
    parse.add_argument('--commit-message')
    parse.add_argument('--sha', help='SHA that pull request head must match to allow merge.')
    parse.add_argument('--merge-method',
                       help='Merge method to use. Possible values are merge, squash or rebase.')

    parse.add_argument('--user')
    return parse


def main():
    args = parser().parse_args()
    github.init(user=args.user)
    repository = github.Repository(args.repository)

    # find the PR
    kwargs = vars(args)
    kwargs = {k: kwargs[k] for k in ['head', 'base', 'pull_number'] if kwargs[k] is not None}
    kwargs['state'] = 'open'
    prs = repository.pull_requests(**kwargs)

    if len(prs) != 1:
        print(f"There are {len(prs)} PRs matching the filter criteria")
        sys.exit(1)

    # sanity checks
    sha = prs[0]['merge_commit_sha']
    if args.sha and sha != args.sha:
        print(f"Requested sha does not match that of the PR")
        sys.exit(1)

    # do the merge
    kwargs = vars(args)
    kwargs = {k: kwargs[k] for k in ['commit_title', 'commit_message', 'merge_method']
              if kwargs[k] is not None}
    if 'commit_title' not in kwargs:
        title = f"Merge Pull Request #{prs[0]['number']} from {prs[0]['head']['label']}"
        kwargs['commit_title'] = title
    if 'commit_message' not in kwargs:
        kwargs['commit_message'] = f"{prs[0]['title']}"

    kwargs['sha'] = sha
    kwargs['pull_number'] = prs[0]['number']
    print('merge kwargs:', kwargs)
    repository.pull_requests.merge(**kwargs)


if __name__ == '__main__':
    main()
