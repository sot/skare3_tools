#!/usr/bin/env python3
"""
Create a pull request
"""

import argparse
from skare3_tools import github


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('--repository',
                       required=True, help='repository name. Example: sot/chandra_aca')
    parse.add_argument('--title', required=True)
    parse.add_argument('--head', help='branch you are merging from', required=True)
    parse.add_argument('--base', help='branch you are merging to', required=True)
    parse.add_argument('--body', required=True)
    parse.add_argument('--user', required=False)
    return parse


def main():
    args = parser().parse_args()
    github.init(user=args.user)
    repository = github.Repository(args.repository)
    repository.pull_requests.create(title=args.title,
                                    head=args.head,
                                    base=args.base,
                                    body=args.body
                                    )


if __name__ == '__main__':
    main()
