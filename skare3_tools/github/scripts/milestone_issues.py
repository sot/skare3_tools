#!/usr/bin/env python3

"""
Get milestone-related issues from a Github repository .
"""

import argparse

import jinja2

from skare3_tools.github import graphql as github


def milestone_issues(milestone):
    query = jinja2.Template(github.REPO_ISSUES_QUERY).render(
        owner="sot", name="skare3", label='"Package update"'
    )
    info = github.GITHUB_API(query)["data"]["repository"]["issues"]
    nodes = sorted(info["nodes"], key=lambda n: n["title"])
    nodes = [
        issue
        for issue in nodes
        if issue["milestone"] and issue["milestone"]["title"] == milestone
    ]
    return nodes


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="sot/skare3")
    parser.add_argument("--milestone")
    return parser


def main():
    args = get_parser().parse_args()
    github.init()
    issues = milestone_issues(args.milestone)
    issues = sorted(issues, key=lambda i: int(i["number"]))
    for issue in issues:
        print(f'Fixes #{issue["number"]}')


if __name__ == "__main__":
    main()
