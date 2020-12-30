#!/usr/bin/env python3
"""
Amend a release description to mention merges after previous release.

This script takes the sha of a release. It checks the commits between the time of this release and
time of the previous release. If there is no previous release, it will look into all commits.
Note that the releases could be on different branches, so the assumption is that all releases
come from the same branch.
"""

import argparse
import re
import sys
from skare3_tools import github, packages


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('--repository',
                       required=True, help='repository name. Example: sot/chandra_aca')
    parse.add_argument('--sha', help='sha of the release')
    parse.add_argument('--token', '-t', help='Github token, or name of file that contains token')
    return parse


def main():
    args = parser().parse_args()
    github.init(token=args.token)
    repository = github.Repository(args.repository)

    # get all releases and find the one we are working on
    releases = repository.releases()
    releases = [r for r in releases if not r['draft'] and not r['prerelease']]
    releases = sorted(releases, key=lambda r: r['tag_name'], reverse=True)
    release_commits = [packages._get_release_commit(repository, r["tag_name"]) for r in releases]
    release_shas = [c['sha'] for c in release_commits]
    i_1 = None
    for i, sha in enumerate(release_shas):
        if sha == args.sha:
            i_1 = i
    if i_1 is None:
        raise Exception(f'Release with sha {args.sha} was not found')

    # get all commits between this release and the previous one, if any.
    kwargs = {'until': repository.commits(ref=release_shas[i_1])['commit']['author']['date']}
    if i_1 + 1 < len(releases):
        kwargs['since'] = repository.commits(ref=release_shas[i_1 + 1])['commit']['author']['date']
    commits = repository.commits(sha='master', **kwargs)[:-1]  # remove the last one, the release

    # get commit messages matching the standard merge commit
    merges = []
    for commit in commits:
        msg = commit['commit']['message']
        match = re.match(
            'Merge pull request (?P<pr>.+) from (?P<branch>\S+)\n\n(?P<description>.+)', msg)
        if match:
            msg = match.groupdict()
            if msg["pr"][0] == '#':
                msg["pr"] = f'[{msg["pr"]}]' \
                            f'(https://github.com/{args.repository}/pull/{msg["pr"][1:]})'
            merges.append(f'PR {msg["pr"]}: {msg["description"]}')
    if merges:
        # edit the release to include the merge information
        release_id = releases[i_1]['id']
        body = releases[i_1]['body']
        if body:
            body += "\n\n"
        body += 'Includes the following merges:\n'
        for merge in merges:
            body += f'- {merge}\n'

        r = repository.releases.edit(release_id, body=body)
        if not r['response']['ok']:
            sys.exit((f"Failed to edit release '{releases[i_1]['name']}'"
                      f" ({release_id}): {r['response']['reason']}"))


if __name__ == '__main__':
    main()
