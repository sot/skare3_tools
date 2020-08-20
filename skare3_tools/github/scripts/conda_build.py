#!/usr/bin/env python

import sys
import argparse
from skare3_tools import github


def ok_or_exit(response, msg):
    if not response['response']['ok']:
        rc = response['response']['status_code']
        msg2 = response['response']['message']
        print(f'{msg} ({rc}): {msg2}')
        sys.exit(1)


def parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages', nargs='+')
    return parser


def main():
    args = parser().parse_args()
    for repo in args.packages:
        repository = github.Repository(repo)
        r = repository.dispatch_event(event_type='conda-build')
        ok_or_exit(r, f'Failed to trigger conda build of {repo}')
        print(f'Building {repo}')


if __name__ == '__main__':
    main()
