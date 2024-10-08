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

The package list is cached locally. The cache expires after one day.
To use this module to get the package list, use :func:`~skare3_tools.packages.get_package_list`::

    >>> from skare3_tools import packages
    >>> pkgs = packages.get_package_list()
    >>> pkgs[0]
    {'name': 'ska3-core',
     'package': 'ska3-core',
     'repository': None,
     'owner': None}

Package Info
------------

Some information about each package is cached locally. The cache expires whenever there is an
"update" or a "push" to the associated Github repository. The information includes information such
as the number of open pull requests, number of branches. It also includes versions available in
conda channels.

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

import argparse
import datetime
import glob
import json
import logging
import os
import re
import subprocess
import sys
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


def json_cache(name, directory="", ignore=None, expires=None, update_policy=None):
    r"""
    Decorator to cache function results in json format.

    This decorator adds an 'update' argument to decorated functions. update is False by default,
    but one can set it to True to force-update the cache entry.

    Data is saved in json files. The file names can include a special separator character to denote
    the function arguments. Currently that character is ':'.

    :param name:
    :param directory: str
        path where to save json file. Either absolute or relative to CONFIG['data_dir']
    :param ignore: list
        list of argument names to ignore in the cache entry identifier
    :param expires: dict
        a dictionary that can be given to datetime.timedelta(\*\*expires)
        If the cache entry is older than this interval, it is updated.
    :param update_policy: callable
        A callable taking two arguments: (filename, result), which returns True if the cache entry
        should be updated.
    :return:
    """
    import inspect
    from functools import wraps

    directory = os.path.normpath(os.path.join(CONFIG["data_dir"], directory))
    if not ignore:
        ignore = []
    if expires:
        expires = datetime.timedelta(**expires)

    def decorator_cache(func, ignore_args=ignore, expiration=expires, name=name):
        signature = inspect.signature(func)
        name += "::"

        @wraps(func)
        def wrapper(*args, update=False, **kwargs):
            s_args = signature.bind(*args, **kwargs).arguments
            arg_str = "-".join(
                [
                    "{a}:{v}".format(a=a, v=s_args[a])
                    for a in s_args
                    if a not in ignore_args
                ]
            )
            filename = "{name}{arg_str}.json".format(name=name, arg_str=arg_str)
            # in an ideal world, filename would be completely sanitized... this world is not ideal.
            filename = filename.replace(os.sep, "-")
            filename = os.path.join(directory, filename)
            if expiration is not None and os.path.exists(filename):
                m_time = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
                update = update or (datetime.datetime.now() - m_time > expiration)
            result = None
            if os.path.exists(filename):
                with open(filename) as file:
                    result = json.load(file)
            if update_policy is not None and result is not None:
                update = update or update_policy(filename, result)
            if not dir_access_ok(filename):
                logging.getLogger("skare3").debug(
                    f"No write access to cache file {filename}"
                )
                update = False
            if result is None or update:
                result = func(*args, **kwargs)
                if update:
                    directory_out = os.path.dirname(filename)
                    if not os.path.exists(directory_out):
                        os.makedirs(directory_out)
                    with open(filename, "w") as file:
                        json.dump(result, file)
            return result

        def clear_cache():
            files = os.path.join(directory, "{name}*.json".format(name=name))
            files = glob.glob(files)
            if files:
                subprocess.run(["rm"] + files, check=False)

        wrapper.clear_cache = clear_cache

        sig = inspect.signature(func)

        def rm_cache_entry(*args, s=sig, **kwargs):
            s_args = s.bind(*args, **kwargs).arguments
            arg_str = "-".join(
                [
                    "{a}:{v}".format(a=a, v=s_args[a])
                    for a in s_args
                    if a not in ignore_args
                ]
            )
            filename = os.path.join(
                directory, "{name}{arg_str}.json".format(name=name, arg_str=arg_str)
            )
            if os.path.exists(filename):
                os.remove(filename)

        wrapper.rm_cache_entry = rm_cache_entry
        return wrapper

    return decorator_cache


def _ensure_skare3_local_repo(update=True):
    repo_dir = os.path.join(CONFIG["data_dir"], "skare3")
    parent = os.path.dirname(repo_dir)
    if not os.path.exists(parent):
        os.makedirs(parent)
    if not os.path.exists(repo_dir):
        _ = subprocess.run(
            ["git", "clone", "https://github.com/sot/skare3", repo_dir],
            cwd=CONFIG["data_dir"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    elif update:
        _ = subprocess.run(
            ["git", "pull"],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    assert os.path.exists(repo_dir)


def _conda_package_list(update=True):
    _ensure_skare3_local_repo(update)
    all_meta = glob.glob(
        os.path.join(CONFIG["data_dir"], "skare3", "pkg_defs", "*", "meta.yaml")
    )
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


@json_cache("pkg_name_map", expires={"days": 1})
def get_package_list():
    """
    Return a list of dictionaries, one per package.

    :return: dict
        Dictionary contains only basic information
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
            jinja2.Template(query).render(name=name, owner=owner, cursor=at, **kwargs)
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
                )
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
        api(jinja2.Template(github.graphql.REPO_QUERY).render(name=name, owner=owner))
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
            requests.get(c.format(**os.environ), timeout=2)
        except KeyError as e:
            # this clears the exception we just caugh and raises another one
            raise Exception(
                "Missing expected environmental variable: {e}".format(e=str(e))
            ) from None
        except requests.ConnectTimeout:
            c2 = urllib.parse.urlparse(c)
            c2 = urllib.parse.urlunparse(
                (
                    c2.scheme,
                    c2.netloc.split("@")[-1],
                    c2.path,
                    c2.params,
                    c2.query,
                    c2.fragment,
                )
            )
            unreachable.append(c2)
        cmd += ["--channel", c.format(**os.environ)]

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


def _get_repository_info_v3(
    owner_repo,
    since=7,
    include_unreleased_commits=False,
    include_commits=False,
):
    """
    Get information about a Github repository.

    This uses Github API v3. This function is DEPRECATED, use v4 instead.

    :param owner_repo: str
        the name of the repository, including owner, something like 'sot/skare3'.
    :param since: int or str
        the maximum number of releases to look back, or the release tag to look back to
        (not inclusive).
    :param include_unreleased_commits: bool
        whether to include commits and merges for repositories that have no release.
        This affects only top-level entries 'commits', 'merges', 'merge_info'.
        It is for backward compatibility with the dashboard.
    :param include_commits: bool
        whether to include commits in release_info.
    :return:
    """
    api = github.GITHUB_API_V3

    owner, repo = owner_repo.split("/")
    repository = github.Repository(owner_repo)

    releases = [
        release
        for release in repository.releases()
        if not release["prerelease"] and not release["draft"]
    ]

    # get the actual commit sha and date for each release
    release_commits = [_get_release_commit(repository, r["tag_name"]) for r in releases]
    release_commits = [repository.commits(ref=c["sha"]) for c in release_commits]
    release_dates = {
        r["tag_name"]: c["commit"]["committer"]["date"]
        for r, c in zip(releases, release_commits, strict=True)
    }

    date_since = None
    if isinstance(since, int):
        # only the latest 'since' releases (at most) will be included in summary
        if len(releases) > since:
            date_since = sorted(release_dates.values(), reverse=True)[since]
    elif since in release_dates:
        # only releases _after_ 'since' will be included in summary
        date_since = release_dates[since]
    else:
        raise Exception(
            "Requested repository info with since={since},".format(since=since)
            + "which is not and integer and is not one of the known releases"
            + "({releases})".format(releases=sorted(release_dates.keys()))
        )

    release_info = [
        {"release_tag": "", "release_tag_date": "", "commits": [], "merges": []}
    ]

    all_pull_requests = repository.pull_requests(state="all")
    all_pull_requests = {pr["number"]: pr for pr in all_pull_requests}
    commits = repository.commits(
        sha=repository.info["default_branch"], since=date_since
    )
    if date_since is not None:
        commits = commits[:-1]  # remove first commit, which was just the starting point
    for commit in commits:
        sha = commit["sha"]
        releases_at_commit = [
            {
                "release_tag": release["tag_name"],
                "release_tag_date": release["published_at"],
                "commits": [],
                "merges": [],
            }
            for release in [
                r
                for r, c in zip(releases, release_commits, strict=True)
                if c["sha"] == sha
            ]
        ]
        release_info += releases_at_commit

        release_info[-1]["commits"].append(
            {
                "sha": commit["sha"],
                "message": commit["commit"]["message"],
                "date": commit["commit"]["committer"]["date"],
                "author": commit["commit"]["author"]["name"],
            }
        )
        match = re.match(
            r"Merge pull request #(?P<pr_number>.+) from (?P<branch>\S+)\n\n(?P<title>.+)",
            commit["commit"]["message"],
        )
        if match:
            merge = match.groupdict()
            merge["pr_number"] = int(merge["pr_number"])
            if merge["pr_number"] in all_pull_requests:
                merge["title"] = all_pull_requests[merge["pr_number"]]["title"].strip()
            release_info[-1]["merges"].append(merge)

    if len(release_info) > 1:
        last_tag = release_info[1]["release_tag"]
        last_tag_date = release_info[1]["release_tag_date"]
    else:
        last_tag = ""
        last_tag_date = ""

    branches = repository.branches()
    issues = [i for i in repository.issues() if "pull_request" not in i]

    pull_requests = []
    for pr in repository.pull_requests():
        pr_commits = api.get(pr["commits_url"]).json()
        date = pr_commits[-1]["commit"]["committer"]["date"]
        pull_requests.append(
            {
                "number": pr["number"],
                "url": pr["_links"]["html"]["href"],
                "title": pr["title"],
                "n_commits": len(pr_commits),
                "last_commit_date": date,
            }
        )

    headers = {"Accept": "application/vnd.github.antiope-preview+json"}
    workflows = api.get(
        "/repos/{owner}/{repo}/actions/workflows".format(owner=owner, repo=repo),
        headers=headers,
    ).json()
    workflows = [
        {k: w[k] for k in ["name", "badge_url"]} for w in workflows["workflows"]
    ]

    repo_info = {
        "owner": owner,
        "name": repo,
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


_LAST_UPDATED_QUERY = jinja2.Template(
    """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    pushedAt
    updatedAt
    name
    owner  {
      id
    }
  }
}
"""
)


def repository_info_is_outdated(_, pkg_info):
    """
    Cache update policy that returns True if the Github repository has been updated or pushed into.

    If the calling user has not write access to the cache directory, this function returns False,
    unless SKARE3_REPO_INFO_LATEST is set to "True".

    :param _:
    :param pkg_info: dict. As returned from :func:`~skare3_tools.packages.get_repository_info`.
    :return:
    """
    update = os.environ.get("SKARE3_REPO_INFO_LATEST", "").lower() in ["true", "1"]
    if not dir_access_ok(CONFIG["data_dir"]) and not update:
        return False
    result = github.GITHUB_API_V4(_LAST_UPDATED_QUERY.render(**pkg_info))
    result = result["data"]["repository"]
    outdated = (
        pkg_info["pushed_at"] < result["pushedAt"]
        or pkg_info["updated_at"] < result["updatedAt"]
    )
    return outdated


def get_repository_info(owner_repo, version="v4", **kwargs):
    """
    Get information about a Github repository

    :param owner_repo: str
        the name of the repository, including owner, something like 'sot/skare3'.
    :param since: int or str
        the maximum number of releases to look back, or the release tag to look back to
        (not inclusive).
    :param include_unreleased_commits: bool
        whether to include commits and merges for repositories that have no release.
        This affects only top-level entries 'commits', 'merges', 'merge_info'.
        It is for backward compatibility with the dashboard.
    :param include_commits: bool
        whether to include commits in release_info.
    :param version: str
        Github API version to use.
    :param update: bool
        Force update of the cached info. By default updates only if pushed_at or updated_at change.
    :return:
    """
    # the indirect call is to make sure the version argument is set at this point
    # otherwise, there are two caches if the version is explicitly set to the default value
    # (one where it is set and one where it is not)
    return _get_repository_info(owner_repo, version, **kwargs)


@json_cache(
    "pkg_repository_info",
    directory="pkg_info",
    update_policy=repository_info_is_outdated,
)
def _get_repository_info(owner_repo, version, **kwargs):
    owner, name = owner_repo.split("/")

    if version == "v4":
        info = _get_repository_info_v4(owner_repo, **kwargs)
    else:
        info = _get_repository_info_v3(owner_repo, **kwargs)

    info["master_version"] = ""
    conda_info = get_conda_pkg_info(name, conda_channel="masters")
    if name.lower() in conda_info:
        info["master_version"] = conda_info[name.lower()][-1]["version"]

    return info


get_repository_info.clear_cache = _get_repository_info.clear_cache
get_repository_info.rm_cache_entry = _get_repository_info.rm_cache_entry


def get_repositories_info(repositories=None, version="v4", update=False):
    if repositories is None:
        repositories = [
            p["repository"]
            for p in get_package_list()
            if p["owner"] in CONFIG["organizations"]
        ]
    repo_package_map = {
        p["repository"]: p["package"] for p in get_package_list() if p["repository"]
    }

    info = {"packages": []}
    meta_pkg_versions = {
        pkg: {r: "" for r in repositories} for pkg in ["ska3-flight", "ska3-matlab"]
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
                assert (
                    owner_repo in repo_package_map
                ), "Package {owner_repo} not in package map".format(
                    owner_repo=owner_repo
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
        # print(owner_repo)
        try:
            repo_info = get_repository_info(owner_repo, version=version, update=update)
            repo_info["matlab"] = meta_pkg_versions["ska3-matlab"][owner_repo]
            repo_info["flight"] = meta_pkg_versions["ska3-flight"][owner_repo]
            info["packages"].append(repo_info)
        except Exception as e:
            logging.warning("Failed to get info on %s: %s", owner_repo, e)
            continue

    info.update({"time": datetime.datetime.now().isoformat()})

    return info


def get_parser():
    description = """
SkaRE3 Github information tool.

This script queries Github and a few other sources to determine the status of all packages.
"""

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "-o",
        default="repository_info.json",
        help="Output file (default=repository_info.json)",
    )
    parser.add_argument(
        "--token", help="Github token, or name of file that contains token"
    )
    return parser


def main():
    args = get_parser().parse_args()

    github.init(token=args.token)

    info = get_repositories_info()
    if info:
        with open(args.o, "w") as f:
            json.dump(info, f, indent=2)


if __name__ == "__main__":
    main()
