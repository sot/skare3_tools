#!/usr/bin/env python3
"""
Create the MATLAB Jira issue for a ska3-matlab release.

Finds the release pull request in sot/skare3 (the PR whose title is the release
version) and the Matlab Tools release it ships with, and creates a "Problem
Report" issue in the MATLAB project at https://occ-cfa.cfa.harvard.edu.

The Matlab Tools release comes from the release milestone in sot/skare3: the
PR's milestone, or else the milestone whose title names the version or the
--matlab-release. The proper title is "2026.13 (MATLAB 2026_060)", but
"2026.13" and "MATLAB 2026_060" are also recognized.

The issue description links the release PR and includes the PR's executive
summary (the "This PR includes:" list), converted to Jira wiki markup. The
authenticated user is set as the issue's Developer.

Jira authentication uses a Personal Access Token, created once at
https://occ-cfa.cfa.harvard.edu (avatar -> Profile -> Personal Access Tokens)
and passed with --token or the FSDS_JIRA_TOKEN environment variable.
Use --dry-run to review the issue content without creating anything.
"""

import argparse
import json
import logging
import re
import sys

from skare3_tools import github, jira
from skare3_tools.scripts.fsds_issue import (
    HEADING,
    find_pr,
    markdown_to_jira,
    replace_pr_with_release,
)

logger = logging.getLogger(__name__)

SKARE3_REPO = "sot/skare3"

INTRO = (
    "The ska3 release for {matlab_release} will be {version}. "
    "This is the corresponding PR: [{url}]"
)

# "2026.13 (MATLAB 2026_060)", "2026.13" or "MATLAB 2026_060"
MILESTONE_TITLE = re.compile(
    r"(?P<version>\d{4}\.\d+)?"
    r"\s*"
    r"(?:\(?MATLAB\s+(?P<matlab_release>\d{4}_\d{3})\)?)?",
    flags=re.IGNORECASE,
)


def executive_summary(body):
    """
    Return the executive summary of a release PR description.

    The executive summary is the text between the title heading (if there is
    one) and the next heading. Headings inside fenced code blocks are ignored.
    """
    lines = body.splitlines()
    if lines and HEADING.match(lines[0]):
        lines = lines[1:]
    summary = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
        elif not in_code and HEADING.match(line):
            break
        summary.append(line)
    summary = "\n".join(summary).strip()
    if not summary:
        logger.warning("No executive summary found in the PR description")
    return summary


def build_description(version, matlab_release, pr):
    """Intro sentence linking the PR, followed by the PR's executive summary."""
    description = INTRO.format(
        matlab_release=matlab_release, version=version, url=pr["html_url"]
    )
    summary = executive_summary(pr["body"] or "")
    if summary:
        description += "\n\n" + markdown_to_jira(replace_pr_with_release(summary))
    return description.rstrip() + "\n"


def parse_milestone_title(title):
    """
    Get the (ska3-matlab version, Matlab Tools release) named in a milestone title.

    The proper title is "2026.13 (MATLAB 2026_060)", but "2026.13" and
    "MATLAB 2026_060" also happen. Missing parts are None, and so are both parts
    for any other title.
    """
    match = MILESTONE_TITLE.fullmatch(title.strip())
    if match is None:
        return None, None
    return match.group("version"), match.group("matlab_release")


def find_milestone(version, matlab_release=None, pr=None):
    """
    Find the title of the sot/skare3 milestone for a ska3-matlab release.

    The milestone of the release PR is used if it has one. Otherwise, the
    milestone is the one whose title names the version or the Matlab Tools
    release. Exits if there is no such milestone or more than one.
    """
    if pr is not None and pr.get("milestone"):
        return pr["milestone"]["title"]
    matches = []
    for milestone in github.Repository(SKARE3_REPO).milestones(state="all"):
        title_version, title_matlab_release = parse_milestone_title(milestone["title"])
        if title_version == version or (
            matlab_release is not None and title_matlab_release == matlab_release
        ):
            matches.append(milestone["title"])
    wanted = f"'{version}'" + (f" or 'MATLAB {matlab_release}'" if matlab_release else "")
    if not matches:
        sys.exit(f"No milestone in {SKARE3_REPO} matches {wanted}")
    if len(matches) > 1:
        for title in matches:
            print(f"  {title}", file=sys.stderr)
        sys.exit(f"More than one milestone in {SKARE3_REPO} matches {wanted}")
    return matches[0]


def get_matlab_release(version, matlab_release=None, pr=None):
    """
    Get the Matlab Tools release for a ska3-matlab version.

    It comes from the release milestone (see `find_milestone`) or from
    `matlab_release`. Exits if the two disagree, if the milestone names a
    different version, or if neither gives the Matlab Tools release.
    """
    title = find_milestone(version, matlab_release, pr)
    title_version, title_matlab_release = parse_milestone_title(title)
    if title_version is not None and title_version != version:
        sys.exit(f"Milestone '{title}' is not for version {version}")
    if matlab_release is None:
        matlab_release = title_matlab_release
    elif title_matlab_release not in (None, matlab_release):
        sys.exit(f"Milestone '{title}' is not for MATLAB {matlab_release}")
    if matlab_release is None:
        sys.exit(
            f"Milestone '{title}' does not name the Matlab Tools release. "
            "Use --matlab-release to give it (e.g. --matlab-release 2026_060)."
        )
    return matlab_release


def build_fields(version, matlab_release, pr, developer=None):
    """
    Build the Jira issue fields for a ska3-matlab release PR.

    The custom fields are Release (11600) and Developer (11900).
    Assignee and the other fields are left to their Jira defaults.
    """
    fields = {
        "project": {"key": "MATLAB"},  # pid 10112
        "issuetype": {"id": "10101"},  # Problem Report
        "summary": f"Python updates for ska3-matlab (Release {matlab_release})",
        "description": build_description(version, matlab_release, pr),
        "customfield_11600": matlab_release,
    }
    if developer is not None:
        fields["customfield_11900"] = [{"name": developer}]
    return fields


def parser():
    parse = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parse.add_argument("version", help="ska3-matlab release version (e.g. 2026.13)")
    parse.add_argument(
        "--matlab-release",
        help=(
            "Matlab Tools release (e.g. 2026_060). Needed if the milestone title"
            " does not include it. Default: from the milestone title"
        ),
    )
    parse.add_argument(
        "--pr", type=int, help="PR number in sot/skare3 (skips the title search)"
    )
    parse.add_argument(
        "--token",
        "-t",
        help=(
            "Jira Personal Access Token, or name of file that contains the token."
            " Default: the FSDS_JIRA_TOKEN environment variable."
            " Create the token in Jira (avatar -> Profile -> Personal Access Tokens)"
        ),
    )
    parse.add_argument("--github-token", help="Github token")
    parse.add_argument("--jira-url", default=jira.JIRA_URL, help=argparse.SUPPRESS)
    parse.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the issue fields without creating anything",
    )
    return parse


def main():
    # print() carries the tool's output (the dry-run payload and the created
    # issue URL); logging carries status and diagnostics (to stderr).
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parser().parse_args()
    github.init(token=args.github_token)
    pr = find_pr(args.version, args.pr)
    matlab_release = get_matlab_release(args.version, args.matlab_release, pr)
    if args.dry_run:
        fields = build_fields(args.version, matlab_release, pr)
        print(fields["description"])
        print(json.dumps(fields, indent=2))
        return
    try:
        session = jira.get_session(token=args.token)
        user = jira.verify(session, url=args.jira_url)
        logger.info("Authenticated as %s", user.get("displayName", user.get("name")))
        fields = build_fields(args.version, matlab_release, pr, developer=user["name"])
        result = jira.create_issue(session, fields, url=args.jira_url)
    except jira.JiraError as error:
        sys.exit(str(error))
    print(f"Created {result['key']}: {args.jira_url}/browse/{result['key']}")


if __name__ == "__main__":
    main()
