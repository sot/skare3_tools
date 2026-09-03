#!/usr/bin/env python3
r"""
A module to keep track of all package information (repository, conda package info, etc).

Package List
------------

One of the main purposes of this module is to maintain a list of "packages". Some packages have an
associated github repository, which can be owned by one or more organizations. Some packages
have an associated conda package, which is listed in one or more conda channels. The package list is
the union of the conda packages and the github repositories. The name of the package, the name of
the repository and the name of the conda package might not be the same.

To assemble the package list, this module uses:

- All skare3/pkg_defs/\*/meta.yaml files within the skare3 repository
- the list of all repositories for a given list of organizations (sot, acisops)

The package list is produced by ``skare3-refresh`` and read from the data store, so getting it
needs neither a Github token nor a conda query. To use this module to get the package list, use
:func:`~skare3_tools.packages.get_package_list`::

    >>> from skare3_tools import packages
    >>> pkgs = packages.get_package_list()
    >>> pkgs[0]
    {'name': 'ska3-core',
     'package': 'ska3-core',
     'repository': None,
     'owner': None}

Package Info
------------

Information about each package is read from the data store, which ``skare3-refresh`` rebuilds
hourly (see :mod:`skare3_tools.packages.store`). It includes information such as the number of open
pull requests and the number of branches, and the versions installed at each deployment stage
(``master_version``, ``flight``, ``matlab``, ``aca`` and the tested version).

Passing ``update=True``, or any argument the store does not hold (such as a different ``since``),
queries Github directly instead. That needs a token, and is much slower.

To get the current information associated with a package using
:func:`~skare3_tools.packages.get_repository_info`::

    >>> from skare3_tools import packages
    >>> pkg = packages.get_repository_info('sot/Quaternion')
    >>> pkg.keys()
    dict_keys(['owner', 'name', 'pushed_at', 'updated_at', 'last_tag', 'last_tag_date',
    'commits', 'merges', 'merge_info', 'release_info', 'issues', 'n_pull_requests',
    'branches', 'pull_requests', 'workflows', 'master_version'])

The information on all packages can be accessed with
:func:`~skare3_tools.packages.get_repositories_info`::

    >>> from skare3_tools import packages
    >>> pkg = packages.get_repositories_info()

Conda Info
----------

As part of the call to get_repository_info, the conda package versions are also fetched. This is
done with :func:`~skare3_tools.packages.get_conda_pkg_info`, something like::

    >>> from skare3_tools import packages
    >>> info = packages.get_conda_pkg_info('quaternion')

By default, this function looks for information on packages from a set of channels specified as
the "main" channels. Extra sets of channels (i.e.: test, masters, shiny) can be specified as part
of the :ref:`Configuration`, in which case one can do::

    >>> from skare3_tools import packages
    >>> info = packages.get_conda_pkg_info('quaternion', conda_channel='masters')

"""

import contextlib
import datetime
import glob
import inspect
import io
import json
import logging
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib
from pathlib import Path

import jinja2
import requests
import yaml
from packaging.version import InvalidVersion, Version

from skare3_tools import github
from skare3_tools.config import CONFIG


class NetworkException(Exception):
    pass


class RecipesUnavailable(Exception):
    """The skare3 recipes, which define the package universe, could not be fetched."""


_DEFAULT_CLIENT = None


def _data_client():
    """
    The process-wide default reader for the data store.

    One client is reused so repeated calls do not re-read -- or re-fetch over
    HTTP -- the whole aggregate. It remembers what it read, so a long-lived
    process that wants fresh data should build its own
    :class:`~skare3_tools.packages.DataClient`.
    """
    global _DEFAULT_CLIENT  # noqa: PLW0603
    if _DEFAULT_CLIENT is None:
        # local import: client.py builds on this module
        from skare3_tools.packages.client import DataClient

        _DEFAULT_CLIENT = DataClient()
    return _DEFAULT_CLIENT


def dir_access_ok(path):
    """
    Returns true if the given path has write access or can be created.
    """
    path = Path(path).resolve()
    if os.path.exists(path):
        return os.access(path, os.W_OK)
    # if path does not exist, climb up the hierarchy to see if it can be created
    if path.parent != path:
        return dir_access_ok(path.parent)
    return False


@contextlib.contextmanager
def _skare3_recipes():
    """
    The skare3 ``pkg_defs`` directory, fetched into a temporary directory.

    The recipes define the package universe, and they are read once per run.
    They used to live in a git checkout inside the data directory, which meant
    a working tree in shared, rsynced storage: it could go stale, be clobbered
    by anything else writing there, and a caller without write access to it
    would silently ``git pull`` into nothing and carry on with whatever
    happened to be on disk.

    A tarball of the default branch is one request and leaves nothing behind,
    so every run reads a defined state and a failure to fetch is unmistakable.

    :yield: Path. The pkg_defs directory.
    :raises RecipesUnavailable: if the recipes cannot be fetched or unpacked.
    """
    owner_repo = urllib.parse.urlparse(CONFIG["repository"]).path.strip("/")
    with tempfile.TemporaryDirectory(prefix="skare3-recipes-") as tmp:
        # no ref in the path: the API resolves the repository's default branch
        try:
            response = github.GITHUB_API_V3.get(f"/repos/{owner_repo}/tarball")
        except Exception as exc:
            # unreachable, unauthenticated, rate-limited: from here they are one
            # condition, "the recipes are not available", and the caller needs
            # to hear about it rather than get a traceback
            raise RecipesUnavailable(
                f"cannot fetch the {owner_repo} recipes: {exc}"
            ) from exc
        if not response.ok:
            raise RecipesUnavailable(
                f"cannot fetch the {owner_repo} recipes: "
                f"{response.reason} ({response.status_code})"
            )
        try:
            with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
                tar.extractall(tmp, filter="data")
        except (tarfile.TarError, OSError) as exc:
            raise RecipesUnavailable(
                f"cannot unpack the {owner_repo} recipes: {exc}"
            ) from exc
        # the tarball holds a single top-level directory, {owner}-{repo}-{sha}
        roots = [path for path in Path(tmp).iterdir() if path.is_dir()]
        recipes = roots[0] / "pkg_defs" if len(roots) == 1 else None
        if recipes is None or not recipes.is_dir():
            raise RecipesUnavailable(
                f"the {owner_repo} tarball has no pkg_defs directory"
            )
        yield recipes


def _conda_package_list():
    """The packages the skare3 recipes define."""
    with _skare3_recipes() as recipes:
        all_meta = sorted(glob.glob(os.path.join(recipes, "*", "meta.yaml")))
        return _parse_recipes(all_meta)


def _parse_recipes(all_meta):
    all_info = []
    for f in all_meta:
        macro = "{% macro compiler(arg) %}{% endmacro %}\n"
        macro += "{% macro pin_compatible(arg) %}{% endmacro %}\n"
        try:
            info = yaml.load(
                jinja2.Template(macro + open(f).read()).render(environ={}),
                Loader=yaml.FullLoader,
            )
        except jinja2.TemplateError as err:
            parent = os.path.split(os.path.split(f)[-2])[-1]
            logging.getLogger("skare3").error(
                f"Failed to parse recipe for {parent}: {err}"
            )
            continue

        pkg_info = {
            "name": os.path.basename(os.path.dirname(f)),
            "package": info["package"]["name"],
            "repository": None,
            "owner": None,
        }
        if "about" in info and "home" in info["about"]:
            home = info["about"]["home"].strip()
            matches = [
                re.match(r"git@github.com:(?P<org>[^/]+)/(?P<repo>\S+)\.git$", home),
                re.match(r"git@github.com:(?P<org>[^/]+)/(?P<repo>\S+)$", home),
                re.match(r"https?://github.com/(?P<org>[^/]+)/(?P<repo>[^/]+)/?", home),
            ]
            for match in matches:
                if match:
                    org_repo = match.groupdict()
                    pkg_info["owner"] = org_repo["org"]
                    pkg_info["repository"] = "{org}/{repo}".format(**org_repo)
                    pkg_info["home"] = info["about"]["home"]
                    break

        # else:
        #    pkg_info['home'] = ''
        # print(f, pkg_info['repository'])
        all_info.append(pkg_info)
    return all_info


def _package_list_from_github():
    """
    Assemble the package list from the skare3 recipes and the organizations.

    This is the producer-side function: it pulls the local skare3 clone and
    lists the organizations' repositories. Readers should use
    :func:`get_package_list`, which reads the store.

    :return: list of dict
        Each dictionary contains only basic information.
    """
    all_packages = _conda_package_list()
    full_names = [p["repository"] for p in all_packages]
    organizations = [github.Organization(org) for org in CONFIG["organizations"]]
    repositories = [r for org in organizations for r in org.repositories()]
    for r in repositories:
        if r["full_name"] in full_names:
            continue
        all_packages.append(
            {
                "name": r["full_name"],
                "package": None,
                "repository": r["full_name"],
                "owner": r["owner"]["login"],
            }
        )
    all_packages = sorted(
        all_packages,
        key=lambda p: (str(p["repository"]) if p["repository"] else "", p["name"]),
    )
    return all_packages


def get_package_list(update=False):
    """
    Return a list of dictionaries, one per package.

    Read from the data store, which needs neither a Github token nor a conda
    query. ``update=True`` assembles the list from the skare3 recipes and the
    organizations instead.

    :param update: bool
        Assemble the list from Github instead of reading the store.
    :return: list of dict
        Each dictionary contains only basic information.
    """
    if update:
        return _package_list_from_github()
    return _data_client().package_list()


def _get_tag_target(tag):
    if "target" in tag:
        return _get_tag_target(tag["target"])
    else:
        return tag["oid"], tag["committedDate"]


# I did not assemble these queries in my mind.
# If you need to change one of these queries,
# go to https://docs.github.com/en/graphql/overview/explorer
# copy the query into the dialog, edit the template parameters
# (you can remove the 'before: "{{ cursor }}"' part)
# run it to see it works, then click where it says "explorer"
# and that should bring up a tree view where you can click to edit the query.

_PR_QUERY = """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    name
    owner {
      login
    }
    pullRequests(last: 100, before: "{{ cursor }}") {
      nodes {
        number
        title
        url
        mergeCommit {
            oid
        }
        commits(last: 100) {
          totalCount
          nodes {
            commit {
              committedDate
              pushedDate
              message
            }
          }
        }
        baseRefName
        headRefName
        author {
          ... on User {
            name
          }
        }
        state
      }
      pageInfo {
        hasPreviousPage
        hasNextPage
        startCursor
        endCursor
      }
    }
  }
}
"""


_COMPARE_COMMITS_QUERY = """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    ref(qualifiedName: "{{ base }}") {
      compare(headRef: "{{ head }}") {
        aheadBy
        behindBy
        commits(first: 100, after: "{{ cursor }}") {
          nodes {
            oid
            message
            pushedDate
            author {
              user {
                  login
              }
            }
          }
          pageInfo {
            hasPreviousPage
            hasNextPage
            startCursor
            endCursor
          }
        }
      }
    }
  }
}
"""


_COMMIT_QUERY = """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    name
    owner {
      login
    }
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, after: "{{ cursor }}") {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              oid
              message
              pushedDate
              author {
                user {
                  login
                }
              }
            }
          }
        }
      }
    }
  }
}
"""


class Dict(dict):
    def __getitem__(self, i):
        if i in self.keys():
            return super().__getitem__(i)
        return self.node(self, i)

    @staticmethod
    def _node(root, path):
        if path:
            return Dict._node(root[path[0]], path[1:])
        return root

    @staticmethod
    def node(root, path):
        path = path.split("/")
        return Dict._node(root, path)


def get_all_nodes(
    owner, name, path, query, query_2=None, at="", reverse=False, **kwargs
):
    if reverse:
        cursor = "startCursor"
        has_more = "hasPreviousPage"
    else:
        cursor = "endCursor"
        has_more = "hasNextPage"
    data = Dict(
        github.GITHUB_API_V4(
            jinja2.Template(query).render(name=name, owner=owner, cursor=at, **kwargs),
            org=owner,
        )
    )
    check_api_errors(data)
    commits = data[path]["nodes"]
    if query_2 is None:
        query_2 = query
    while data[path]["pageInfo"][has_more]:
        if at == data[path]["pageInfo"][cursor]:
            raise RuntimeError("Cursor did not change and will cause an infinite loop")

        at = data[path]["pageInfo"][cursor]
        data = Dict(
            github.GITHUB_API_V4(
                jinja2.Template(query_2).render(
                    name=name, owner=owner, cursor=at, **kwargs
                ),
                org=owner,
            )
        )
        check_api_errors(data)
        commits += data[path]["nodes"]
    return commits


def check_api_errors(data):
    if "errors" in data:
        try:
            msg = "\n".join([e["message"] for e in data["errors"]])
        except Exception:
            raise Exception(str(data["errors"])) from None
        raise Exception(msg)


def _pr_commits(commits, all_pull_requests):
    merges = []
    pulls_v_hash = {
        pr["mergeCommit"]["oid"]: pr
        for pr in all_pull_requests.values()
        if pr["mergeCommit"] is not None
    }
    for commit in commits:
        match = re.match(
            r"Merge pull request #(?P<pr_number>.+) from (?P<branch>\S+)(\n\n(?P<title>.+))?",
            commit["message"],
        )
        if commit["oid"] in pulls_v_hash:
            merge = {
                "pr_number": pulls_v_hash[commit["oid"]]["number"],
                "title": pulls_v_hash[commit["oid"]]["title"],
                "branch": pulls_v_hash[commit["oid"]]["headRefName"],
                "author": pulls_v_hash[commit["oid"]]["author"]["name"],
            }
            merges.append(merge)
        elif match:
            # I don't think it will ever enter this branch
            # this would be recognizable in the dashboard because the PR author is unknown
            merge = match.groupdict()
            merge["pr_number"] = int(merge["pr_number"])
            merge["author"] = "Unknown"
            merges.append(merge)

    return merges


def _get_repository_info_v4(
    owner_repo,
    since=7,
    include_unreleased_commits=False,
    include_commits=False,
):
    owner, name = owner_repo.split("/")
    api = github.GITHUB_API_V4
    data_v4 = Dict(
        api(
            jinja2.Template(github.graphql.REPO_QUERY).render(name=name, owner=owner),
            org=owner,
        )
    )
    if "errors" in data_v4:
        try:
            msg = "\n".join([e["message"] for e in data_v4["errors"]])
        except Exception:
            raise Exception(str(data_v4["errors"])) from None
        raise Exception(msg)

    branches = [
        n
        for n in data_v4["data/repository/refs/nodes"]
        if re.match("heads/", n["name"])
    ]
    releases = data_v4["data/repository/releases/nodes"]
    issues = data_v4["data/repository/issues/nodes"]
    default_branch = data_v4["data/repository/defaultBranchRef/name"]

    commits_path = "data/repository/defaultBranchRef/target/history"
    commits = data_v4[commits_path]["nodes"]
    if data_v4[commits_path]["pageInfo"]["endCursor"] is not None:
        # append the rest of the commits only if there were commits to begin with
        commits += get_all_nodes(
            owner,
            name,
            commits_path,
            _COMMIT_QUERY,
            reverse=False,
            at=data_v4[commits_path]["pageInfo"]["endCursor"],
        )

    pull_requests_path = "data/repository/pullRequests"
    pull_requests = data_v4[pull_requests_path]["nodes"]
    if data_v4[pull_requests_path]["pageInfo"]["startCursor"] is not None:
        # append the rest of the PRs only if there were commits to begin with
        pull_requests += get_all_nodes(
            owner,
            name,
            pull_requests_path,
            _PR_QUERY,
            reverse=True,
            at=data_v4[pull_requests_path]["pageInfo"]["startCursor"],
        )

    # from now, keep a list of the open pull requests on the main branch
    all_pull_requests = {pr["number"]: pr for pr in pull_requests}
    pull_requests = [
        pr
        for pr in pull_requests
        if pr["state"] not in ["CLOSED", "MERGED"]
        and pr["baseRefName"] == default_branch
    ]
    pull_requests = [
        {
            "number": pr["number"],
            "author": pr["author"]["name"],
            "url": pr["url"],
            "title": pr["title"],
            "n_commits": pr["commits"]["totalCount"],
            "last_commit_date": pr["commits"]["nodes"][-1]["commit"]["pushedDate"],
        }
        for pr in pull_requests
    ]
    pull_requests = sorted(pull_requests, key=lambda pr: pr["number"], reverse=True)

    # get release info since "since", excluding drafts, pre-releases, invalid versions
    releases = [r for r in releases if not r["isPrerelease"] and not r["isDraft"]]
    exclude = []
    for rel in releases:
        rel["tag_oid"], rel["committed_date"] = _get_tag_target(rel["tag"])
        try:
            Version(rel["tagName"])
        except InvalidVersion:
            logging.debug(
                f"{owner_repo} release {rel['tagName']} does not conform to PEP 440. "
                "It will be ignored"
            )
            exclude += [rel["tagName"]]
    releases = [r for r in releases if r["tagName"] not in exclude]
    releases = sorted(releases, key=lambda r: Version(r["tagName"]), reverse=True)

    release_tags = [r["tagName"] for r in releases]
    if isinstance(since, int):
        # keeping the last "since" releases, plus the current main branch
        releases = releases[: since + 1]
    elif since in release_tags:
        # keeping up to the "since" tag (inclusive), plus the current main branch
        releases = releases[: release_tags.index(since) + 2]
    elif since is not None:
        raise Exception(
            "Requested repository info with since={since},".format(since=since)
            + "which is not and integer and is not one of the known releases"
            + "({release_tags})".format(release_tags=release_tags)
        )

    if len(releases) == 0:
        # if there are no releases, look for merge messages in all commits
        rel_prs = _pr_commits(commits, all_pull_requests)
    else:
        # if there are releases, look for merge messages in the commits since the last release
        rel_commits = get_all_nodes(
            owner,
            name,
            "data/repository/ref/compare/commits",
            _COMPARE_COMMITS_QUERY,
            reverse=False,
            base=releases[0]["tagName"],
            head=default_branch,
        )
        rel_prs = _pr_commits(rel_commits, all_pull_requests)

    # the first entry in release_info does not correspond to a release
    # it's the list of PRs (and commits) waiting to be released.
    release_info = [
        {
            "release_tag": "",
            "release_tag_date": "",
            "release_commit_date": datetime.datetime.now().isoformat(),
            "commits": [],
            "merges": rel_prs,
        }
    ]

    for base, head in zip(releases[1:], releases[:-1], strict=True):
        rel_commits = get_all_nodes(
            owner,
            name,
            "data/repository/ref/compare/commits",
            _COMPARE_COMMITS_QUERY,
            reverse=False,
            base=base["tagName"],
            head=head["tagName"],
        )
        rel_prs = _pr_commits(rel_commits, all_pull_requests)
        release = {
            "release_sha": head["tag_oid"],
            "release_commit_date": head["committed_date"],
            "release_tag": head["tagName"],
            "release_tag_date": head["publishedAt"],
            "commits": [],
            "merges": rel_prs,
        }
        release_info.append(release)

    # the first entry in the list is not a release, but the current main branch
    release_info = release_info[:1] + sorted(
        release_info[1:], key=lambda r: Version(r["release_tag"]), reverse=True
    )

    if len(release_info) > 1:
        last_tag = release_info[1]["release_tag"]
        last_tag_date = release_info[1]["release_tag_date"]
    else:
        last_tag = ""
        last_tag_date = ""

    # workflows are only in v3
    headers = {"Accept": "application/vnd.github.antiope-preview+json"}
    workflows = github.GITHUB_API_V3.get(
        "/repos/{owner}/{name}/actions/workflows".format(owner=owner, name=name),
        headers=headers,
    ).json()
    workflows = [
        {k: w[k] for k in ["name", "badge_url"]} for w in workflows["workflows"]
    ]

    repo_info = {
        "owner": owner,
        "name": name,
        "pushed_at": data_v4["data"]["repository"]["pushedAt"],
        "updated_at": data_v4["data"]["repository"]["updatedAt"],
        "last_tag": last_tag,
        "last_tag_date": last_tag_date,
        "commits": len(release_info[0]["commits"]),
        "merges": len(release_info[0]["merges"]),
        "merge_info": release_info[0]["merges"],
        "release_info": release_info,
        "issues": len(issues),
        "n_pull_requests": len(pull_requests),
        "branches": len(branches),
        "pull_requests": pull_requests,
        "workflows": workflows,
    }

    if not include_commits:
        for r in repo_info["release_info"]:
            del r["commits"]

    if not include_unreleased_commits and len(repo_info["release_info"]) == 1:
        repo_info["commits"] = 0
        repo_info["merges"] = 0
        repo_info["merge_info"] = []

    return repo_info


def _strip_credentials(url):
    parts = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(parts._replace(netloc=parts.netloc.split("@")[-1]))


def _channel_is_reachable(url, tries=4, timeout=5, wait=5):
    """
    Probe a channel URL, retrying transient network errors.

    Read timeouts on cxc are not uncommon; give the server a few chances
    before declaring the channel unreachable.
    """
    for attempt in range(1, tries + 1):
        try:
            requests.get(url, timeout=timeout)
            return True
        except (requests.Timeout, requests.ConnectionError):
            # credentials stripped: the url embeds CONDA_PASSWORD
            logging.getLogger("skare3").warning(
                "channel %s not responding (attempt %d/%d)",
                _strip_credentials(url),
                attempt,
                tries,
            )
            if attempt < tries:
                time.sleep(wait)
    return False


def get_conda_pkg_info(conda_package, conda_channel=None):
    """
    Get information on a conda package.

    :param conda_package: str
        Name of conda package
    :param conda_channel: str
        url of the channel
    :return: dict
    """
    if sys.version_info == 3 >= (3, 7):
        kwargs = {"capture_output": True}
    else:
        kwargs = {"stdout": subprocess.PIPE}
    cmd = ["conda", "search", conda_package, "--override-channels", "--json"]
    if conda_channel is None:
        conda_channels = CONFIG["conda_channels"]["main"]
    elif isinstance(conda_channel, list):
        conda_channels = conda_channel
    elif conda_channel in CONFIG["conda_channels"]:
        conda_channels = CONFIG["conda_channels"][conda_channel]
    else:
        conda_channels = [conda_channel]
    unreachable = []
    for c in conda_channels:
        try:
            url = c.format(**os.environ)
        except KeyError as e:
            # this clears the exception we just caught and raises another one
            raise Exception(
                "Missing expected environmental variable: {e}".format(e=str(e))
            ) from None
        if not _channel_is_reachable(url):
            unreachable.append(_strip_credentials(url))
        cmd += ["--channel", url]

    if unreachable:
        msg = "The following conda channels are not reachable:\n -"
        msg += " -".join(unreachable)
        raise NetworkException(msg)

    p = subprocess.run(cmd, check=False, **kwargs)
    out = json.loads(p.stdout.decode())
    if (
        "error" in out
        and "exception_name" in out
        and out["exception_name"] == "PackagesNotFoundError"
    ):
        out = {}
    if "error" in out:
        if "message" in out:
            raise Exception(out["message"])
        else:
            raise Exception(str(out))
    for key in out:
        for pkg in out[key]:
            pkg["depends"] = _split_versions(pkg["depends"])
    return out


def _split_versions(depends):
    """
    Convert a list of package dependencies into a dictionary of the form {name: version}.

    Typically, "depends" comes from calling `conda search ska3-flight --info --json`.
    This function expects each row to be of the form "name==version" or "name version".
    If the version is not given, it is set to ''.
    """
    result = {}
    for depend in depends:
        if "==" in depend:
            name_version = depend.split("==", maxsplit=1)
        else:
            name_version = depend.split(maxsplit=1)
        if len(name_version) == 2:
            name, version = name_version
        else:
            name, version = name_version[0], ""
        result[name.strip()] = version.strip()
    return result


def get_conda_pkg_dependencies(conda_package, conda_channel=None):
    """
    Get dependencies of a conda package.

    :param conda_package: str
        Name of conda package
    :param conda_channel: str
        url of the channel
    :return: dict
    """
    out = get_conda_pkg_info(conda_package, conda_channel)
    if not out:
        raise Exception(
            "{conda_package} not found.".format(conda_package=conda_package)
        )
    return out[conda_package][-1]["depends"]


def _get_release_commit(repository, release_name):
    """
    Get release commit.

    Quaternion releases 3.4.1 and 3.5.1 give different results.

    :param repository:
    :param release_name:
    :return:
    """
    obj = repository.tags(name=release_name)["object"]
    if obj["type"] == "tag":
        obj = repository.tags(tag_sha=obj["sha"])["object"]
    if obj["type"] != "commit":
        raise Exception("Object is not a commit, but a {t}".format(t=obj["type"]))
    return obj


# derived from the signature, at import, so it cannot drift from it (and so a
# test that fakes out _get_repository_info_v4 does not change what is recorded)
_RECORD_OPTIONS = {
    name: param.default
    for name, param in inspect.signature(_get_repository_info_v4).parameters.items()
    if param.default is not inspect.Parameter.empty
}


def record_options():
    """
    The arguments the records in the data store are produced with.

    ``skare3-refresh`` records these in the aggregate, and
    :func:`get_repository_info` compares its arguments against the *recorded*
    ones to decide whether the store can answer.

    :return: dict
    """
    return dict(_RECORD_OPTIONS)


def get_repository_info(owner_repo, update=False, **kwargs):
    """
    Get information about a Github repository.

    By default this reads the data store, which needs no Github token (see
    :class:`~skare3_tools.packages.DataClient`). The store holds one rendering
    of each repository, so any argument asking for something else -- a
    different ``since``, for instance -- queries Github instead, as does
    ``update=True``.

    :param owner_repo: str
        the name of the repository, including owner, something like 'sot/skare3'.
    :param update: bool
        Query Github directly instead of reading the store.
    :param since: int or str
        the maximum number of releases to look back, or the release tag to look back to
        (not inclusive).
    :param include_unreleased_commits: bool
        whether to include commits and merges for repositories that have no release.
        This affects only top-level entries 'commits', 'merges', 'merge_info'.
        It is for backward compatibility with the dashboard.
    :param include_commits: bool
        whether to include commits in release_info.
    :return: dict
    """
    if update:
        return _repository_info_from_github(owner_repo, **kwargs)
    client = _data_client()
    if kwargs and not _store_holds(client.packages(), kwargs):
        return _repository_info_from_github(owner_repo, **kwargs)
    return client.repository_info(owner_repo)


_MISSING = object()


def _store_holds(aggregate, kwargs):
    """
    Whether the store's records were made with these arguments.

    Compared against the options the *aggregate* records, not this module's
    defaults: if refresh ever changes its window, the answer follows. An
    aggregate that records nothing is not second-guessed.
    """
    stored = aggregate.get("record_options")
    if stored is None:
        return False
    return all(stored.get(name, _MISSING) == value for name, value in kwargs.items())


def _repository_info_from_github(owner_repo, **kwargs):
    """Query Github (and the masters channel) for one repository's record."""
    owner, name = owner_repo.split("/")

    info = _get_repository_info_v4(owner_repo, **kwargs)

    info["master_version"] = ""
    conda_info = get_conda_pkg_info(name, conda_channel="masters")
    if name.lower() in conda_info:
        info["master_version"] = conda_info[name.lower()][-1]["version"]

    return info


def get_repositories_info(repositories=None, update=False):
    """
    Get information about many Github repositories.

    By default this reads the data store (see
    :class:`~skare3_tools.packages.DataClient`); ``update=True`` queries Github
    directly instead, which needs a token and is much slower.

    :param repositories: list of str
        Repositories ("owner/name") to report on. Default: all of them.
        Repositories the store does not know about are reported and skipped.
    :param update: bool
        Query Github directly instead of reading the store.
    :return: dict
    """
    if update:
        return _repositories_info_from_github(repositories)
    info = _data_client().packages()
    if repositories is None:
        return info
    wanted = list(repositories)
    known = {f"{p['owner']}/{p['name']}": p for p in info["packages"]}
    missing = [repo for repo in wanted if repo not in known]
    if missing:
        logging.getLogger("skare3").warning(
            "no package data for %s (not in the store)", ", ".join(missing)
        )
    return dict(info, packages=[known[repo] for repo in wanted if repo in known])


def _repositories_info_from_github(repositories=None):
    """Query Github (and the conda channels) for every repository's record."""
    package_list = _package_list_from_github()
    if repositories is None:
        repositories = [
            p["repository"]
            for p in package_list
            if p["owner"] in CONFIG["organizations"]
        ]
    repo_package_map = {
        p["repository"]: p["package"] for p in package_list if p["repository"]
    }

    info = {"packages": []}
    meta_pkg_versions = {
        pkg: dict.fromkeys(repositories, "") for pkg in ["ska3-flight", "ska3-matlab"]
    }

    for pkg in ["ska3-flight", "ska3-matlab"]:
        try:
            assert pkg in meta_pkg_versions
            conda_info = get_conda_pkg_info(pkg, conda_channel="main")
            if pkg not in conda_info:
                raise Exception(f"{pkg} package not found")
            conda_info = conda_info[pkg][-1]
            info[pkg] = conda_info["version"]
            versions = conda_info["depends"]
            for owner_repo in repositories:
                assert owner_repo in repo_package_map, (
                    "Package {owner_repo} not in package map".format(
                        owner_repo=owner_repo
                    )
                )
                conda_pkg = repo_package_map[owner_repo]
                if conda_pkg in versions:
                    assert owner_repo in meta_pkg_versions[pkg]
                    meta_pkg_versions[pkg][owner_repo] = versions[conda_pkg]
        except NetworkException as e:
            logging.error(e)
            raise
        except Exception as e:
            logging.warning("Empty {pkg}: {t}: {e}".format(pkg=pkg, t=type(e), e=e))

    for owner_repo in repositories:
        try:
            repo_info = _repository_info_from_github(owner_repo)
            repo_info["matlab"] = meta_pkg_versions["ska3-matlab"][owner_repo]
            repo_info["flight"] = meta_pkg_versions["ska3-flight"][owner_repo]
            # the store also carries these; keep the key set identical across
            # sources so consumers (the dashboard template) never see them
            # missing, only empty
            repo_info.setdefault("aca", "")
            repo_info.setdefault("perl", "")
            repo_info.setdefault("test_version", "")
            repo_info.setdefault("test_status", "")
            info["packages"].append(repo_info)
        except Exception as e:
            logging.warning("Failed to get info on %s: %s", owner_repo, e)
            continue

    info.update({"time": datetime.datetime.now().isoformat()})

    return info
