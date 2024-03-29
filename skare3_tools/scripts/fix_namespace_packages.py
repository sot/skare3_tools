import argparse
import difflib
import os
import re
import subprocess
from pathlib import Path

import ska_file


def run_check(*args, **kwargs):
    print("Running:", " ".join(args[0]))
    subprocess.run(*args, check=True, **kwargs)


PKGS_MAP = {
    "Chandra.Maneuver": "chandra_maneuver",
    "Chandra.Time": "chandra_time",
    "Chandra.cmd_states": "chandra_cmd_states",
    "Ska.DBI": "ska_dbi",
    "Ska.File": "ska_file",
    "Ska.Matplotlib": "ska_matplotlib",
    "Ska.Numpy": "ska_numpy",
    "Ska.ParseCM": "ska_parsecm",
    "Ska.Shell": "ska_shell",
    "Ska.Sun": "ska_sun",
    "Ska.Table": "ska_table",
    "Ska.TelemArchive": "ska_telemarchive",
    "Ska.arc5gl": "ska_arc5gl",
    "Ska.engarchive": "cheta",
    "Ska.ftp": "ska_ftp",
    "Ska.quatutil": "ska_quatutil",
    "Ska.report_ranges": "ska_report_ranges",
    "Ska.tdb": "ska_tdb",
}

USAGE = """

``skare3-fix-namespace-packages`` is a utility script to flatten namespace package
names like ``Chandra.Maneuver`` to the more standard ``chandra_maneuver``.

Although the namespace versions will continue to be supported, the flattened names are
preferred. This is especially true for developers, where the namespace packages can
cause subtle problems with imports.

This script has a number of modes of operation:
- Show summary information on a number of packages with the intent of bulk updates.
- Show diffs for a single directory and optionally write the changes.
- Make a git branch and commit the changes for one or more repos.
- Make a git branch, commit the changes, and make a GitHub PR for one or more repos.

Print summary information on a number of repos
----------------------------------------------
This will print a summary of the number of fixes needed for each repo:

    # Get all sot repos that are in Ska3 or Non-FSDS
    python clone_git_repos.py

    # Summary
    skare3-fix-namespace-packages --summary-only repos

Fix an arbitrary directory of code files
----------------------------------------
If the directory of code files is not a git repo then we need to be careful about
inspecting the changes and having a way to back them out. Here we first look at the
diffs, where the directory is named `acis_taco`:

  skare3-fix-namespace-packages --diffs acis_taco

If the diffs look good then we can write the changes:

  skare3-fix-namespace-packages --write acis_taco
  find acis_taco -name '*.bak'  # Backups of original files

Git repo with manual PR creation
--------------------------------
If the directory `acis_taco` is a git repo then we can make a branch and commit the
changes.

NOTE: You are responsible for ensuring the repo is up to date with the remote and
checked out at the correct branch.

  skare3-fix-namespace-packages --make-branch acis_taco

The changes will be checked into a `flatten-namespace-package-names` branch:

  git show  # See all the changes

If the changes look good then you can push the branch and make a PR in the usual way
from the command line using `git` commands.

Git repo with automatic PR creation
----------------------------------
If the directory `acis_taco` is a git repo then we can make a branch and commit the
changes and then make a PR in one step.

NOTE: You are responsible for ensuring the repo is up to date with the remote and
checked out at the correct branch.

  skare3-fix-namespace-packages --make-pr --github-token-file=OAUTH acis_taco
"""


def get_argparse():
    parser = argparse.ArgumentParser(usage=USAGE)

    parser.add_argument("dir_names", nargs="*")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Summary information only, no fixes applied",
    )
    parser.add_argument("--diffs", action="store_true", help="Show diffs")
    parser.add_argument(
        "--sort-imports",
        action="store_true",
        help="Sort imports (needed for packages with CI checks of sort order)",
    )
    parser.add_argument(
        "-w",
        "--write",
        action="store_true",
        help="Write back modified files",
    )
    parser.add_argument(
        "-n",
        "--no-backups",
        action="store_true",
        help="Don't write backups for modified files",
    )
    parser.add_argument(
        "-b",
        "--backup-suffix",
        default=".bak",
        help="Backup suffix (default=.bak)",
    )
    parser.add_argument(
        "--make-branch",
        action="store_true",
        help="Make a git branch and commit changes (implies --write)",
    )
    parser.add_argument(
        "--branch-name",
        default="flatten-namespace-package-names",
        help="Branch name to use if --make-branch is set",
    )
    parser.add_argument(
        "--make-pr",
        action="store_true",
        help="Make a GitHub pull request for the changes (implies --make-branch)",
    )
    parser.add_argument(
        "--github-token-file",
        type=Path,
        help=(
            "Path to GitHub token file for making a PR "
            "(if not supplied use GITHUB_TOKEN environment variable)"
        ),
    )

    return parser


def flatten_namespace_pkgs(file_or_dir, opt: argparse.Namespace):
    # Find every *.py file in the "repo_name" directory using Path
    file_or_dir = Path(file_or_dir)
    files = file_or_dir.rglob("*.py") if file_or_dir.is_dir() else [file_or_dir]
    fixes_needed = 0
    for file in files:
        fixes_needed += flatten_name_pkgs_for_file(file, opt)
    return fixes_needed


def flatten_name_pkgs_for_file(file: Path, opt: argparse.Namespace):
    text_orig = file.read_text()
    text = text_orig
    # Not very fast but it should work
    for pkg_old, pkg_new in PKGS_MAP.items():
        text = re.sub(rf"\b{pkg_old}\b", pkg_new, text)
        if pkg_old in text:
            print(f"WARNING: {pkg_old} still found by grepping {file}")

    fix_needed = text != text_orig
    if fix_needed and not opt.summary_only:
        fixing = " ... fixing" if opt.write else ""
        print(f" - {file}{fixing}")
        if opt.diffs:
            for line in difflib.unified_diff(text_orig.splitlines(), text.splitlines()):
                print(line)
        elif opt.write:
            if opt.no_backups:
                file.write_text(text)
            else:
                file.rename(str(file) + opt.backup_suffix)
                file.write_text(text)

            # Fix import order and potential new unused imports. Note that both ruff and
            # Pylance seem to fail in determining that a namespace package import is
            # unused.
            run_check(["ruff", "--select", "F401,I001", "--fix", str(file)])

    return fix_needed


def make_branch(dir_name: Path, opt: argparse.Namespace):
    with ska_file.chdir(dir_name):
        run_check(["git", "switch", "-c", opt.branch_name])


def commit_changes(dir_name: Path, _: argparse.Namespace):
    with ska_file.chdir(dir_name):
        run_check(["git", "commit", "-a", "-m", "Flatten namespace packages"])


def make_pr(dir_name: Path, opt: argparse.Namespace):
    with ska_file.chdir(dir_name):
        run_check(["git", "push", "-u", "origin", opt.branch_name])
        run_check(["gh", "pr", "create", "--fill"])


def main():
    opt = get_argparse().parse_args()
    if opt.summary_only:
        opt.diffs = False
        opt.write = False
        opt.make_branch = False
        opt.make_pr = False

    if opt.github_token_file:
        # gh cli uses the GITHUB_TOKEN environment variable
        os.environ["GITHUB_TOKEN"] = opt.github_token_file.read_text().strip()

    if opt.make_pr:
        opt.make_branch = True

    if opt.make_branch:
        opt.write = True

    for dir_name in opt.dir_names:
        if not opt.summary_only:
            print(f"Processing {dir_name}")

        dir_path = Path(dir_name)

        if opt.make_branch or opt.make_pr:
            make_branch(dir_path, opt)

        fixes_needed = flatten_namespace_pkgs(dir_path, opt)

        if opt.make_branch:
            commit_changes(dir_path, opt)
            if opt.make_pr:
                make_pr(dir_path, opt)

        if opt.summary_only and fixes_needed > 0:
            # Any project with pyproject.toml or ruff.toml is using ruff or isort
            imports_sorted = any(
                (dir_path / config).exists()
                for config in ["ruff.toml", "pyproject.toml"]
            )
            sort_imports_str = " (use --sort-imports)" if imports_sorted else ""
            print(f"{dir_path}: {fixes_needed}{sort_imports_str}")


if __name__ == "__main__":
    main()
