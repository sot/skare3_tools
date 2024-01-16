import argparse
import os
import subprocess
from pathlib import Path

import ska_file
import yaml

from skare3_tools import github

USAGE = """
skare3-clone-git-repos --help

This script clones or updates git repos from GitHub.  It is intended to be used to
create or maintain a local copy of all repos in an org (e.g. sot). This can be useful
for doing bulk updates or for doing specialized searches across all repos if the GitHub
search functionality is not sufficient.

This script is somewhat experts-only and does not have guard rails.
"""


def get_argparse():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "repo_names",
        nargs="*",
        help="Repo names to clone or update (default is all applicable repos in org)",
    )
    parser.add_argument(
        "--repos-dir",
        default="repos",
        help="Output directory for repos (default=repos)",
    )
    parser.add_argument(
        "--all-packages",
        action="store_true",
        help=(
            "Update all packages in org (default is "
            "only sot org ska3-flight and non-FSDS packages)"
        ),
    )
    parser.add_argument(
        "--org",
        default="sot",
        help="GitHub org (default=sot)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run only",
    )
    parser.add_argument(
        "--github-token-file",
        type=Path,
        help=(
            "Path to GitHub token file for reading repos from source org "
            "(if not supplied use GITHUB_TOKEN environment variable)"
        ),
    )
    return parser


def get_ska3_pkgs() -> list[str]:
    """Return list of Ska packages in ska3-flight or non-FSDS environment"""
    # TODO get this from GitHub instead
    user_git = Path.home() / "git"
    ska3_flight = yaml.safe_load(
        open(user_git / "skare3" / "pkg_defs" / "ska3-flight" / "meta.yaml")
    )
    pkgs = [pkg.split()[0] for pkg in ska3_flight["requirements"]["run"]]
    for pkg_remove in [
        "ska3-core",
        "ska3-template",
        "acis_thermal_check",
        "acispy",
        "backstop_history",
    ]:
        pkgs.remove(pkg_remove)

    ska3_non_fsds = yaml.safe_load(
        open(user_git / "skare3" / "environment-non-fsds.yml")
    )
    pkgs.extend(ska3_non_fsds["dependencies"])
    return sorted(pkgs)


def update_repo(repos_dir, name, url):
    path = Path(repos_dir) / name
    if path.exists():
        print("Updating", name)
        with ska_file.chdir(path):
            for branch in ["master", "main"]:
                # fmt: off
                # Non-zero return code means branch doesn't exist
                if (
                    subprocess.call(["git", "switch", branch]) == 0
                    and subprocess.call(["git", "pull", "origin", branch]) == 0
                ):
                # fmt: on
                    break
            else:
                raise Exception("bad return code")
            subprocess.run(["git", "clean", "-fdx"], check=True)
    else:
        with ska_file.chdir(repos_dir):
            print("Cloning", name)
            retcode = subprocess.call(["git", "clone", url])
            if retcode:
                raise Exception()


def get_org_repos(org="sot", token=None):
    github.init(token=token)
    org = github.Organization(org)
    org_repos = org.repositories()
    return org_repos


def get_fake_repo(repo_name, org):
    out = {"name": repo_name, "clone_url": f"https://github.com/{org}/{repo_name}.git"}
    return out


def main(argv=None):
    args = get_argparse().parse_args(argv)

    repos_dir = Path(args.repos_dir)
    repos_dir.mkdir(exist_ok=True, parents=True)

    if args.repo_names:
        repos = [get_fake_repo(name, org=args.org) for name in args.repo_names]
    else:
        if args.all_packages:
            if args.github_token_file is None:
                token = os.environ["GITHUB_TOKEN"]
            else:
                token = args.github_token_file.read_text().strip()
            repos_org = get_org_repos(org=args.org, token=token)
            repos = repos_org
        else:
            repos = [get_fake_repo(name, org=args.org) for name in get_ska3_pkgs()]

    for repo in repos:
        url = repo["clone_url"]
        name = repo["name"]
        print(f"********* {repos_dir}/{name} {url}  *********")
        if not args.dry_run:
            update_repo(repos_dir, name, url)
        print()


if __name__ == "__main__":
    main()
