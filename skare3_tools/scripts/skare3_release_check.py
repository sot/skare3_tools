#!/usr/bin/env python3
"""
Check the environment and conda configuration files to determine which packages to build, if any.

It also does a sanity check, checking consistency between release tag and branch. It is assumed that
the 'target' version (the version after all tests pass) is the name of the branch where the release
is made. This script checks the meta information of all ska3-* packages to see which ones have
version equal to the target version and adds those to a list of packages to build.

This script makes the following checks:

* the given tag exists and follows PEP 0440 format (https://www.python.org/dev/peps/pep-0440),
* there is an existing release with this tag,
* the tag's branch must be named '<release>' or '<release>-<label>',
* there exists a PR based on this branch,
* if tag_name contains an alpha/beta/candidate version, then release must be a pre-release,
* if tag_name contains a label, then release must be a pre-release,
* if GITHUB_SHA is defined, it must be the release commit.
  If not, the local copy of the skare3 repo must be in the tag branch.
"""

import argparse
import glob
import logging
import jinja2
import os
import re
import sys

import git
import yaml

from skare3_tools import github

logging.basicConfig(level="INFO")


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument("--version", required=True, help="Target version to build")
    parse.add_argument(
        "--skare3-path", default=".", help="local copy of the skare3 repo"
    )
    parse.add_argument(
        "--repository", default="sot/skare3", help="Github repository name"
    )
    parse.add_argument(
        "--token", "-t", help="Github token, or name of file that contains token"
    )
    parse.add_argument(
        "--no-check",
        dest="ci_sanity_check",
        action="store_false",
        default=True,
        help="Checks for CI",
    )
    return parse


def log(msg, level=logging.ERROR):
    logging.log(level, msg)
    if level > logging.INFO and "GITHUB_STEP_SUMMARY" in os.environ:
        mode = "r+" if os.path.exists(os.environ["GITHUB_STEP_SUMMARY"]) else "w"
        with open(os.environ["GITHUB_STEP_SUMMARY"], mode) as fh:
            fh.write(f"{msg}\n")


def main():
    arg_parser = parser()
    args = arg_parser.parse_args()
    args.skare3_path = os.path.abspath(args.skare3_path)

    git_repo = None
    try:
        git_repo = git.Repo(args.skare3_path)
    except git.NoSuchPathError:
        log(
            f'--skare3-path points to non-existent directory "{args.skare3_path}".'
        )
    except git.InvalidGitRepositoryError:
        log(
            f'--skare3-path points to an invalid git repo "{args.skare3_path}".'
        )
    if git_repo is None:
        sys.exit(1)

    tag_name = args.version.strip("/").split("/")[
        -1
    ]  # versions can be git refs like refs/tags/V2
    # regular expression (mostly) matching PEP-0440 version format
    fmt = (
        r"(?P<final_version>((?P<epoch>[0-9]+)!)?(?P<release>[0-9]+(\.[0-9]+(\.[0-9]+)?)?))"
        r"((a|b|rc)(?P<rc>[0-9]+))?(\+(?P<label>[a-zA-Z]+))?$"
    )
    version_info = re.match(fmt, tag_name)
    if not version_info:
        log(
            "Tag name must conform to PEP-440 format"
            " (https://www.python.org/dev/peps/pep-0440)"
        )
        sys.exit(2)
    version_info = version_info.groupdict()

    allowed_names = [f"{version_info['final_version']}-branch"]
    if version_info["label"]:
        allowed_names += [f'{version_info["final_version"]}+{version_info["label"]}']

    log(f"Sanity check for release {tag_name}", level=logging.INFO)

    github.init(token=args.token)
    repository = github.Repository(args.repository)

    tag = repository.tags(name=tag_name)
    release = repository.releases(tag_name=tag_name)
    if not release["prerelease"]:
        allowed_names += ["master"]

    # some sanity checks
    fail = []
    if args.ci_sanity_check:
        """
        The following checks that:
        - release exists
        - release tag exists
        - the branch where the tag was made must be in the allowed_names list
        - there is a PR based on this branch
        - the tag branch name must be the final_release version, or <final_version>-<label>
        - if tag_name contains an alpha/beta/candidate version, then release must be a pre-release
        - if tag_name contains a label, then release must be a pre-release
        - if GITHUB_SHA is defined, it must be the release commit.
          If not, the local copy of the skare3 repo must be in the tag branch.
        """
        try:
            if "response" not in release or not release["response"]["ok"]:
                fail.append(f"Release {tag_name} does not exist")
            if "response" not in tag or not tag["response"]["ok"]:
                fail.append(f"Tag {tag_name} does not exist")
            branch_name = ""
            if not fail:
                branch_name = release["target_commitish"]
                pulls = repository.pull_requests(
                    state="open" if release["prerelease"] else "all",
                    head=f'sot:{version_info["final_version"]}-branch',
                )
                pulls = [
                    p for p in pulls if p["title"] == version_info["final_version"]
                ]
                if branch_name not in allowed_names:
                    fail.append(
                        f'Invalid branch name "{branch_name}" for release "{tag_name}". '
                        f'Allowed branch names for this tag are {", ".join(allowed_names)}'
                    )
                if not pulls:
                    fail.append(
                        f"There is no pull request titled {version_info['final_version']}"
                        f" from sot:{version_info['final_version']}-branch into master."
                    )
                if version_info["rc"] is not None and not release["prerelease"]:
                    fail.append(
                        f"Release {tag_name} is marked as a candidate, "
                        f"but the release is not a prerelease"
                    )
                if version_info["label"] is not None and not release["prerelease"]:
                    fail.append(
                        f'Release {tag_name} has label {version_info["label"]}, '
                        f"but the release is not a prerelease"
                    )
            # when workflow triggered by release, GITHUB_SHA must have the release commit sha
            if "GITHUB_SHA" in os.environ:
                if os.environ["GITHUB_SHA"] != tag["object"]["sha"]:
                    fail.append(
                        f"Tag {tag_name} sha differs from sha in GITHUB_SHA: "
                        f"{tag['object']['sha']} != {os.environ['GITHUB_SHA']}"
                    )
            elif git_repo.active_branch.name != branch_name:
                fail.append(
                    f"Current branch is different from release branch "
                    f'("{git_repo.active_branch.name}" != "{branch_name}")'
                )
        except Exception as e:
            exc_type = sys.exc_info()[0].__name__
            fail.append(f"Unexpected error ({exc_type}): {e}")

        if fail:
            log("## Errors")
            for fh in fail:
                log(f"- {fh}")
            sys.exit(3)

    # at this point, branch_name must be set, and it is taken to be the target version
    log(f"Target version {tag_name}", level=logging.INFO)

    # checking package versions
    # whenever a version equals `branch_name`, replace it by the full version.
    files = glob.glob(os.path.join(args.skare3_path, "pkg_defs", "ska3-*", "meta.yaml"))
    packages = []
    possible_error = []
    version_str = str(version_info["final_version"])
    try:
        version_float = str(float(version_info["final_version"]))
    except Exception:
        version_float = None
    for filename in files:
        with open(filename) as fh:
            data = yaml.load(fh, Loader=yaml.SafeLoader)
            version_pkg = str(data["package"]["version"])
            if version_str == version_pkg:
                packages.append(data["package"]["name"])
            elif (
                version_str != version_float
                and version_float == version_pkg
            ):
                # versions like 2024.10 are "tricky" because if you interpret them as floats
                # you get a different value. A typical error in meta.yaml is to write
                #    version: 2024.10
                # instead of
                #    version: "2024.10"
                # causing the version to be interpreted as 2024.1
                # and because this does not match the target version, the package is not built.
                # however, we can't know for sure that this is an error
                # (e.g. ska3-core 2024.1 and ska3-flight 2024.10 is possible)
                possible_error.append(data["package"]["name"])

    if possible_error:
        msg = (
            f"The following package(s) have a version that does not match {version_str}, "
            f"but it matches {version_float} (which is {version_str} interpreted as a float). "
            "They will not be built."
        )
        log(f"{msg}\n", level=logging.WARNING)
        for pkg in possible_error:
            log(f"- {pkg}", level=logging.WARNING)

    if not packages:
        logging.warning("No packages to build. Something must be wrong.")
        sys.exit(4)

    packages_str = " ".join(packages)
    prerelease = release["prerelease"]
    overwrite_flag = f"--skare3-overwrite-version {version_info['final_version']}:{tag_name}\n"

    log(f"prerelease: {prerelease}", level=logging.INFO)
    log(f"packages: {packages_str}", level=logging.INFO)
    log(
        f"overwrite_flag: --skare3-overwrite-version {version_info['final_version']}:{tag_name}",
        level=logging.INFO
    )

    # this output defines variables 'prerelease', 'packages', and 'overwrite_flag'
    if "GITHUB_OUTPUT" in os.environ:
        mode = "r+" if os.path.exists(os.environ["GITHUB_OUTPUT"]) else "w"
        with open(os.environ["GITHUB_OUTPUT"], mode) as fh:
            fh.write(f"prerelease={prerelease}\n")
            fh.write(f"packages={packages_str}\n")
            fh.write(f"overwrite_flag={overwrite_flag}\n")

    # this output will show up in the workflow summary
    if "GITHUB_STEP_SUMMARY" in os.environ:
        template = jinja2.Template(SUMMARY_STRING)
        msg = template.render(
            tag_name=tag_name,
            branch_name=branch_name,
            packages=packages,
            prerelease=prerelease,
            overwrite_flag=overwrite_flag,
        )
        mode = "r+" if os.path.exists(os.environ["GITHUB_STEP_SUMMARY"]) else "w"
        with open(os.environ["GITHUB_STEP_SUMMARY"], mode) as fh:
            fh.write(msg)


SUMMARY_STRING = """
# Release {{ tag_name }}

## Packages to build:

{%for package in packages -%}
- {{ package }}
{%endfor %}
## Arguments:

- `prerelease`: {{ prerelease }}
- `overwrite_flag`: {{ overwrite_flag }}

"""


if __name__ == "__main__":
    main()
