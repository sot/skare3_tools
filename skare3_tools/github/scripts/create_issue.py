#!/usr/bin/env python3
"""
Create a github issue
"""

import argparse
from skare3_tools import github


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('--repository',
                       required=True, help='repository name. Example: sot/chandra_aca')
    parse.add_argument('--title', required=True)
    parse.add_argument('--body', required=True)
    parse.add_argument('--label', default=[], action='append')
    parse.add_argument('--user', required=False)
    return parse


def main():
    args = parser().parse_args()
    github.init(user=args.user)
    repository = github.Repository(args.repository)
    repository.issues.create(title=args.title,
                             body=args.body,
                             labels=args.label)


if __name__ == '__main__':
    main()
