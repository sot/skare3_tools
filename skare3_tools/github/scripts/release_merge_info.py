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

import numpy as np
from packaging.version import Version

from skare3_tools import github, packages


def get_parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument(
        "--repository", required=True, help="repository name. Example: sot/chandra_aca"
    )
    parse.add_argument("--sha", help="sha of the release")
    parse.add_argument("--tag", help="tag of the release")
    parse.add_argument(
        "--token", "-t", help="Github token, or name of file that contains token"
    )
    parse.add_argument(
        "--stdout",
        action="store_true",
        help="print to stdout instead of editing release description",
    )
    return parse


def merges_in_range(repo, sha_1, sha_2):
    commits_1 = repo.commits(sha=sha_1)
    commits_2 = repo.commits(sha=sha_2)
    sha_1 = [c["sha"] for c in commits_1]
    sha_2 = [c["sha"] for c in commits_2]
    i = np.argwhere(np.isin(sha_2, sha_1)).flatten()[0]
    commits = commits_2[:i]
    assert len(commits)  # TODO: shouldn't it be possible with no commits?

    # get commit messages matching the standard merge commit
    merges = []
    for commit in commits:
        msg = commit["commit"]["message"]
        match = re.match(
            r"Merge pull request (?P<pr>.+) from (?P<branch>\S+)(\n\n(?P<description>.+))?",
            msg,
        )
        if match:
            msg = match.groupdict()
            if msg["description"] is None:
                msg["description"] = repo.pull_requests(msg["pr"][1:])[0]["title"]
            merges.append(msg)
    return merges


def main():
    parser = get_parser()
    args = parser.parse_args()

    if not args.tag and not args.sha:
        parser.exit("Need to specify tag or sha")

    github.init(token=args.token)

    repo = github.Repository(args.repository)

    # get all releases and their commit sha
    releases = repo.releases()
    releases = [r for r in releases if not r["draft"] and not r["prerelease"]]
    releases = sorted(releases, key=lambda r: Version(r["tag_name"]), reverse=True)
    releases = {r["tag_name"]: r for r in releases}
    for tag, rel in releases.items():
        releases[tag]["sha"] = packages._get_release_commit(repo, rel["tag_name"])[
            "sha"
        ]

    release_shas = [rel["sha"] for rel in releases.values()]
    releases_by_sha = {rel["sha"]: rel for rel in releases.values()}

    # normalize and check arguments
    if args.tag and not args.sha:
        args.sha = releases[args.tag]["sha"]
    elif args.sha and not args.tag:
        args.tag = releases_by_sha[args.sha]["tag_name"]

    assert args.sha in release_shas, f"Release with sha {args.sha} was not found"
    assert args.tag in releases, f"Release with tag {args.tag} was not found"
    assert releases[args.tag]["sha"] == args.sha, "Inconsistent release sha and tag"

    # now find all merges between the previous release and the requested one
    # checking for commit messages matching the standard merge commit
    merges = merges_in_range(
        repo,
        release_shas[release_shas.index(args.sha) + 1],  # TODO: limit check here?
        args.sha,
    )

    msgs = []
    for merge in merges:
        if merge["pr"][0] == "#":
            merge["pr"] = (
                f'[{merge["pr"]}]'
                f'(https://github.com/{args.repository}/pull/{merge["pr"][1:]})'
            )
        msgs.append(f'PR {merge["pr"]}: {merge["description"]}')

    if msgs:
        # edit the release to include the merge information
        release = releases[args.tag]
        release_id = release["id"]
        body = release["body"]
        if body:
            body += "\n\n"
        body += "Includes the following merges:\n"
        for msg in msgs:
            body += f"- {msg}\n"

        if args.stdout:
            print(body)
        else:
            r = repo.releases.edit(release_id, body=body)
            if not r["response"]["ok"]:
                sys.exit(
                    (
                        f"Failed to edit release '{release['name']}'"
                        f" ({release_id}): {r['response']['reason']}"
                    )
                )


if __name__ == "__main__":
    main()
