#!/usr/bin/env python3
"""
Create the FSDS Jira issue for a ska3-flight release.

Finds the release pull request in sot/skare3 (the PR whose title is the release
version), reformats its description as a Jira "Change Request" issue following
the standard FSDS procedure, and creates the issue in the FSDS project at
https://occ-cfa.cfa.harvard.edu.

The issue description is the PR description up to and including the Testing
section, converted from GitHub markdown to Jira wiki markup.

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

logger = logging.getLogger(__name__)

SKARE3_REPO = "sot/skare3"

CODE_CHANGES = (
    "Detailed list of code changes can be found in the {repo} pull request: {url}"
)
TESTING = (
    "Testing is detailed in the Description below and in individual pull requests."
)
INTERFACE_IMPACTS = "Interface impacts are detailed in the Description below."

HEADING = re.compile(r"^#{1,6}\s")

# Sections kept from the PR description, in addition to the top portion (the
# release title and its summary, before the first "## " heading). Everything
# else -- Review, Deployment, Code changes -- is dropped.
KEEP_SECTIONS = ("interface impacts", "testing")


def truncate_description(body):
    """
    Keep the top portion of the PR description plus the wanted sections.

    The top portion is everything before the first "## " section heading (the
    release title and its summary). After that, only the Interface Impacts and
    Testing sections are kept; the trailing sections (Review, Deployment and
    Code changes) are dropped.
    """
    lines = body.splitlines(keepends=True)
    kept = []
    in_code = False
    in_sections = False
    keep_current = True
    found = False
    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
        elif not in_code and re.match(r"^##\s", line):
            in_sections = True
        if in_sections and not in_code:
            match = re.match(r"^#{1,2}\s+(.*)", line)
            if match:
                title = match.group(1).strip().rstrip(":").lower()
                keep_current = title in KEEP_SECTIONS
                found = found or keep_current
        if keep_current:
            kept.append(line)
    if not found:
        logger.warning(
            "No Interface Impacts or Testing section found; "
            "keeping only the top portion of the description"
        )
    return "".join(kept).rstrip() + "\n"


def replace_pr_with_release(text):
    """
    Replace the word "PR" with "release" in the intro paragraph only.

    The intro is the text between the title heading and the next heading (the
    FSDS procedure describes the change itself as a release, while later
    sections legitimately refer to individual pull requests).
    """
    lines = text.splitlines(keepends=True)
    headings = [i for i, line in enumerate(lines) if HEADING.match(line)]
    if headings and headings[0] == 0:
        start = 1
        end = headings[1] if len(headings) > 1 else len(lines)
    else:
        start = 0
        end = headings[0] if headings else len(lines)
    for i in range(start, end):
        lines[i] = re.sub(r"\bPR\b", "release", lines[i])
    return "".join(lines)


def _split_fenced(text):
    """Split into (is_code, segment) pairs on ``` fences (fence lines dropped)."""
    segments = []
    current = []
    in_code = False
    for line in text.splitlines(keepends=True):
        if line.strip().startswith("```"):
            segments.append((in_code, "".join(current)))
            current = []
            in_code = not in_code
        else:
            current.append(line)
    segments.append((in_code, "".join(current)))
    return [(is_code, segment) for is_code, segment in segments if segment]


def _convert_prose(text):
    text = re.sub(r"^### ", "h3. ", text, flags=re.M)
    text = re.sub(r"^## ", "h2. ", text, flags=re.M)
    text = re.sub(r"^# ", "h1. ", text, flags=re.M)
    text = re.sub(r"^( *)- \[[xX]\] ", r"\1- (/) ", text, flags=re.M)
    text = re.sub(r"^( *)- \[ \] ", r"\1- ", text, flags=re.M)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"[\1|\2]", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"`([^`]+)`", r"{{\1}}", text)
    # nested bullets: 2 spaces of indent per level
    text = re.sub(
        r"^( *)- ",
        lambda m: "*" * (len(m.group(1)) // 2 + 1) + " ",
        text,
        flags=re.M,
    )
    return text


def markdown_to_jira(text):
    """
    Convert GitHub markdown to Jira wiki markup.

    Fenced code blocks become {noformat} blocks and their content is untouched.
    Prose gets headings, checklists, links, bold, inline code and (possibly
    nested) bullet lists converted.
    """
    out = []
    for is_code, segment in _split_fenced(text):
        if is_code:
            out.append("{noformat}\n" + segment + "{noformat}\n")
        else:
            out.append(_convert_prose(segment))
    return "".join(out)


def pr_body_to_jira_description(body):
    """Full PR-body -> Jira-description pipeline."""
    return markdown_to_jira(replace_pr_with_release(truncate_description(body)))


def build_fields(version, pr):
    """
    Build the Jira issue fields for a ska3-flight release PR.

    The custom field ids are the FSDS "Change Request" fields:
    Code Changes (12000), Testing (12001) and Interface Impacts (12002).
    Assignee and the review fields are left to their Jira defaults.
    """
    return {
        "project": {"key": "FSDS"},  # pid 12400
        "issuetype": {"id": "10700"},  # Change Request
        "summary": f"ska3-flight {version}",
        "description": pr_body_to_jira_description(pr["body"]),
        "customfield_12000": CODE_CHANGES.format(repo=SKARE3_REPO, url=pr["html_url"]),
        "customfield_12001": TESTING,
        "customfield_12002": INTERFACE_IMPACTS,
    }


def find_pr(version, pr_number=None):
    """
    Find the release PR in sot/skare3.

    With `pr_number`, fetch that PR directly. Otherwise, search the open PRs
    for exactly one whose title contains the version.
    """
    repository = github.Repository(SKARE3_REPO)
    if pr_number is not None:
        result = repository.pull_requests(pr_number)
        if not isinstance(result, list) or not result:
            sys.exit(f"Could not get PR #{pr_number} from {SKARE3_REPO}: {result}")
        return result[0]
    prs = repository.pull_requests(state="open")
    matches = [pr for pr in prs if version in pr["title"]]
    if not matches:
        sys.exit(f"No open PR in {SKARE3_REPO} with '{version}' in the title")
    if len(matches) > 1:
        for pr in matches:
            print(f"  #{pr['number']}: {pr['title']}", file=sys.stderr)
        sys.exit(f"More than one open PR in {SKARE3_REPO} matches '{version}'")
    return matches[0]


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument("version", help="Release version (e.g. 2026.9)")
    parse.add_argument(
        "--pr", type=int, help="PR number in sot/skare3 (skips the title search)"
    )
    parse.add_argument(
        "--token",
        "-t",
        help="Jira Personal Access Token, or name of file that contains the token",
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
    fields = build_fields(args.version, pr)
    if args.dry_run:
        print(fields["description"])
        print(json.dumps(fields, indent=2))
        return
    try:
        session = jira.get_session(token=args.token)
        user = jira.verify(session, url=args.jira_url)
        logger.info("Authenticated as %s", user.get("displayName", user.get("name")))
        result = jira.create_issue(session, fields, url=args.jira_url)
    except jira.JiraError as error:
        sys.exit(str(error))
    print(f"Created {result['key']}: {args.jira_url}/browse/{result['key']}")


if __name__ == "__main__":
    main()
