#!/usr/bin/env python3
"""
Create a github issue
"""

import sys
import argparse
from skare3_tools import github


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('--repository',
                       required=True, help='repository name. Example: sot/chandra_aca')
    parse.add_argument('--latest-release',
                       help='Repository name (owner/repo). The latest release of this repo'
                            'determines the title and body of issue. Title/body are ignored.')
    parse.add_argument('--title', help='Issue Title. Ignored if --latest-release is given')
    parse.add_argument('--body', help='Issue Description. Ignored if --latest-release is given')
    parse.add_argument('--label', default=[], action='append')
    parse.add_argument('--user', required=False)
    return parse


def ok_or_exit(response, msg):
    if not response['response']['ok']:
        rc = response['response']['status_code']
        msg2 = response['response']['message']
        print(f'{msg} ({rc}): {msg2}')
        sys.exit(1)

def main():
    args = parser().parse_args()
    github.init(user=args.user)
    if args.latest_release:
        release = github.Repository(args.latest_release) .releases(latest=True)
        ok_or_exit(release, f'Failed to create issue after latest release of {args.latest_release}')
        args.title = f"Update {args.latest_release} to {release['name']}"
        args.body = release['body']
    if not args.title or not args.body:
        print('Issue title and body are required unless using --latest-release option.')
        sys.exit(2)
    repository = github.Repository(args.repository)
    issue = repository.issues.create(title=args.title,
                             body=args.body,
                             labels=args.label)
    ok_or_exit(issue, 'Failed to create issue')
    print(f"created issue {issue['number']} at {issue['html_url']}")


if __name__ == '__main__':
    main()
