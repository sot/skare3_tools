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
    parse.add_argument('--title', required=True)
    parse.add_argument('--head', help='branch you are merging from', required=True)
    parse.add_argument('--base', help='branch you are merging to', required=True)
    parse.add_argument('--body', required=True)
    parser.add_argument('--token', '-t', 'Github token, or name of file that contains token')
    return parse


def main():
    args = parser().parse_args()
    github.init(token=args.token)
    repository = github.Repository(args.repository)
    pr = repository.pull_requests.create(title=args.title,
                                         head=args.head,
                                         base=args.base,
                                         body=args.body
                                         )

    if not pr['response']['ok']:
        print('Failed to create pull request')
        sys.exit(1)
    print(f"created pull request {pr['number']} at {pr['html_url']}")


if __name__ == '__main__':
    main()
