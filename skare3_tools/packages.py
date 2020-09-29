#!/usr/bin/env python3
"""
Module to keep track of all package information (repository, conda package info, etc).
"""

import sys
import os
import re
import json
import argparse
import subprocess
import logging
import datetime
import jinja2
import glob
import yaml
import requests
import urllib
from skare3_tools import github
from skare3_tools.config import CONFIG


class NetworkException(Exception):
    pass


def json_cache(name,
               directory='',
               ignore=None,
               expires=None,
               update_policy=None):
    """
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
        a dictionary that can be given to datetime.timedelta(**expires)
        If the cache entry is older than this interval, it is updated.
    :param update_policy: callable
        A callable taking two arguments: (filename, result), which returns True if the cache entry
        should be updated.
    :return:
    """
    from functools import wraps
    import inspect
    directory = os.path.normpath(os.path.join(CONFIG['data_dir'], directory))
    if not ignore:
        ignore = []
    if expires:
        expires = datetime.timedelta(**expires)

    def decorator_cache(func, ignore_args=ignore, expiration=expires, name=name):
        signature = inspect.signature(func)
        name += '::'

        @wraps(func)
        def wrapper(*args, update=False, **kwargs):
            s_args = signature.bind(*args, **kwargs).arguments
            arg_str = '-'.join(['{a}:{v}'.format(a=a, v=s_args[a]) for a in s_args if a not in ignore_args])
            filename = '{name}{arg_str}.json'.format(name=name, arg_str=arg_str)
            # in an ideal world, filename would be completely sanitized... this world is not ideal.
            filename = filename.replace(os.sep, '-')
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
            if result is None or update:
                result = func(*args, **kwargs)
                directory_out = os.path.dirname(filename)
                if not os.path.exists(directory_out):
                    os.makedirs(directory_out)
                with open(filename, 'w') as file:
                    json.dump(result, file)
            return result

        def clear_cache():
            files = os.path.join(directory, '{name}*.json'.format(name=name))
            files = glob.glob(files)
            if files:
                subprocess.run(['rm'] + files)
        setattr(wrapper, 'clear_cache', clear_cache)

        def rm_cache_entry(*args, s=inspect.signature(func), **kwargs):
            s_args = s.bind(*args, **kwargs).arguments
            arg_str = '-'.join(['{a}:{v}'.format(a=a, v=s_args[a]) for a in s_args if a not in ignore_args])
            filename = os.path.join(directory, '{name}{arg_str}.json'.format(name=name, arg_str=arg_str))
            if os.path.exists(filename):
                os.remove(filename)
        setattr(wrapper, 'rm_cache_entry', rm_cache_entry)
        return wrapper
    return decorator_cache


def _ensure_skare3_local_repo(update=True):
    repo_dir = os.path.join(CONFIG['data_dir'], 'skare3')
    parent = os.path.dirname(repo_dir)
    if not os.path.exists(parent):
        os.makedirs(parent)
    if not os.path.exists(repo_dir):
        _ = subprocess.run(['git', 'clone', 'https://github.com/sot/skare3', repo_dir],
                           cwd=CONFIG['data_dir'],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    elif update:
        _ = subprocess.run(['git', 'pull'],
                           cwd=repo_dir,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    assert os.path.exists(repo_dir)


def _conda_package_list(update=True):
    _ensure_skare3_local_repo(update)
    all_meta = glob.glob(os.path.join(CONFIG['data_dir'],
                                      'skare3', 'pkg_defs', '*', 'meta.yaml'))
    all_info = []
    for f in all_meta:
        macro = '{% macro compiler(arg) %}{% endmacro %}\n'
        info = yaml.load(jinja2.Template(macro + open(f).read()).render(), Loader=yaml.FullLoader)
        pkg_info = {
            'name': os.path.basename(os.path.dirname(f)),
            'package': info['package']['name'],
            'repository': None,
            'owner': None
        }
        if 'about' in info and 'home' in info['about']:
            home = info['about']['home'].strip()
            matches = [re.match('git@github.com:(?P<org>[^/]+)/(?P<repo>\S+)\.git$', home),
                       re.match('git@github.com:(?P<org>[^/]+)/(?P<repo>\S+)$', home),
                       re.match('https?://github.com/(?P<org>[^/]+)/(?P<repo>[^/]+)/?', home)]
            m = {}
            for m in matches:
                if m:
                    m = m.groupdict()
                    break
            if m:
                pkg_info['owner'] = m['org']
                pkg_info['repository'] = '{org}/{repo}'.format(**m)
                pkg_info['home'] = info['about']['home']
        # else:
        #    pkg_info['home'] = ''
        # print(f, pkg_info['repository'])
        all_info.append(pkg_info)
    return all_info


@json_cache('pkg_name_map',
            expires={'days': 1})
def get_package_list():
    """
    Return a list of dictionaries, one per package.

    :return: dict
        Dictionary contains only basic information
    """
    all_packages = _conda_package_list()
    full_names = [p['repository'] for p in all_packages]
    organizations = [github.Organization(org) for org in CONFIG['organizations']]
    repositories = [r for org in organizations for r in org.repositories()]
    for r in repositories:
        if r['full_name'] in full_names:
            continue
        all_packages.append({
            'name': r['full_name'],
            'package': None,
            'repository': r['full_name'],
            'owner': r['owner']['login']
        })
    all_packages = sorted(all_packages,
                          key=lambda p: (str(p['repository']) if p['repository'] else '',
                                         p['name']))
    return all_packages


def _get_tag_target(tag):
    if 'target' in tag:
        return _get_tag_target(tag['target'])
    else:
        return tag['oid']


_PR_QUERY = """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    name
    owner {
      login
    }
    pullRequests(last: 100, baseRefName: "master", before: "{{ cursor }}") {
      nodes {
        number
        title
        url
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


_COMMIT_QUERY = """
{
  repository(name: "{{ name }}", owner: "{{ owner }}") {
    name
    owner {
      login
    }
    ref(qualifiedName: "master") {
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
            }
          }
        }
      }
    }
  }
}
"""


def _get_repository_info_v4(owner_repo,
                            since=7,
                            use_pr_titles=True,
                            include_unreleased_commits=False,
                            include_commits=False):
    owner, name = owner_repo.split('/')
    api = github.GITHUB_API_V4
    data_v4 = api(jinja2.Template(github.graphql.REPO_QUERY).render(name=name, owner=owner))
    if 'errors' in data_v4:
        try:
            msg = '\n'.join([e['message'] for e in data_v4['errors']])
        except Exception:
            raise Exception(str(data_v4['errors']))
        raise Exception(msg)

    branches = [n for n in data_v4['data']['repository']['refs']['nodes'] if
                re.match('heads/', n['name'])]
    releases = data_v4['data']['repository']['releases']['nodes']
    commits = data_v4['data']['repository']['ref']['target']['history']['nodes']
    issues = data_v4['data']['repository']['issues']['nodes']

    commit_data = data_v4
    while commit_data['data']['repository']['ref']['target']['history']['pageInfo']['hasNextPage']:
        cursor = commit_data['data']['repository']['ref']['target']['history']['pageInfo']['endCursor']
        commit_data = api(jinja2.Template(_COMMIT_QUERY).render(name=name,
                                                                owner=owner,
                                                                cursor=cursor))
        commits += (commit_data['data']['repository']['ref']['target']['history']['nodes'])

    pr_data = data_v4
    pull_requests = pr_data['data']['repository']['pullRequests']['nodes']
    while pr_data['data']['repository']['pullRequests']['pageInfo']['hasPreviousPage']:
        cursor = pr_data['data']['repository']['pullRequests']['pageInfo']['startCursor']
        pr_data = api(jinja2.Template(_PR_QUERY).render(name=name,
                                                        owner=owner,
                                                        cursor=cursor))
        pull_requests += (pr_data['data']['repository']['pullRequests']['nodes'])

    releases = [r for r in releases if not r['isPrerelease'] and not r['isDraft']]
    for r in releases:
        r['tag_oid'] = _get_tag_target(r['tag'])

    releases = {r['tag_oid']: r for r in releases}
    release_info = [{
        'release_tag': '',
        'release_tag_date': '',
        'commits': [],
        'merges': []
    }]

    all_pull_requests = {pr['number']: pr for pr in pull_requests}
    pull_requests = [pr for pr in pull_requests if pr['state'] not in ['CLOSED', 'MERGED']]
    pull_requests = [{
        'number': pr['number'],
        'url': pr['url'],
        'title': pr['title'],
        'n_commits': pr['commits']['totalCount'],
        'last_commit_date': pr['commits']['nodes'][-1]['commit']['pushedDate'],
    } for pr in pull_requests]
    pull_requests = sorted(pull_requests, key=lambda pr: pr['number'], reverse=True)

    for commit in commits:
        sha = commit['oid']
        if sha in releases:
            release_info.append({
                'release_tag': releases[sha]["tagName"],
                'release_tag_date': releases[sha]["publishedAt"],
                'commits': [],
                'merges': []
            })
        release_info[-1]['commits'].append(commit)
        match = re.match(
            'Merge pull request #(?P<pr_number>.+) from (?P<branch>\S+)\n\n(?P<title>.+)',
            commit['message'])
        if match:
            merge = match.groupdict()
            merge["pr_number"] = int(merge["pr_number"])
            if use_pr_titles:
                if merge["pr_number"] in all_pull_requests:
                    merge["title"] = all_pull_requests[merge["pr_number"]]['title']  # .strip()
            release_info[-1]['merges'].append(merge)

    release_tags = [r['release_tag'] for r in release_info]
    if type(since) is int:
        release_info = release_info[:since+1]
    elif since in release_tags:
        release_info = release_info[:release_tags.index(since)]
    elif since is not None:
        raise Exception('Requested repository info with since={since},'.format(since=since) +
                        'which is not and integer and is not one of the known releases' +
                        '({release_tags})'.format(release_tags=release_tags))

    if len(release_info) > 1:
        last_tag = release_info[1]['release_tag']
        last_tag_date = release_info[1]['release_tag_date']
    else:
        last_tag = ''
        last_tag_date = ''

    # workflows are only in v4
    headers = {'Accept': 'application/vnd.github.antiope-preview+json'}
    workflows = github.GITHUB_API_V3.get(
        '/repos/{owner}/{name}/actions/workflows'.format(owner=owner, name=name),
        headers=headers).json()
    workflows = [{k: w[k] for k in ['name', 'badge_url']} for w in workflows['workflows']]

    repo_info = {
        'owner': owner,
        'name': name,
        'pushed_at': data_v4['data']['repository']['pushedAt'],
        'updated_at': data_v4['data']['repository']['updatedAt'],
        'last_tag': last_tag,
        'last_tag_date': last_tag_date,
        'commits': len(release_info[0]['commits']),
        'merges': len(release_info[0]['merges']),
        'merge_info': release_info[0]['merges'],
        'release_info': release_info,
        'issues': len(issues),
        'n_pull_requests': len(pull_requests),
        'branches': len(branches),
        'pull_requests': pull_requests,
        'workflows': workflows
    }

    if not include_commits:
        for r in repo_info['release_info']:
            del r['commits']

    if not include_unreleased_commits and len(repo_info['release_info']) == 1:
        repo_info['commits'] = 0
        repo_info['merges'] = 0
        repo_info['merge_info'] = []

    return repo_info


def get_conda_pkg_info(conda_package,
                       conda_channel=None):
    """
    Get information on a conda package.

    :param conda_package: str
        Name of conda package
    :param conda_channel: str
        url of the channel
    :return: dict
    """
    if sys.version_info.major == 3 and sys.version_info.minor >= 7:
        kwargs = {'capture_output': True}
    else:
        kwargs = {'stdout': subprocess.PIPE}
    cmd = ['conda', 'search', conda_package, '--override-channels', '--json']
    if conda_channel is None:
        conda_channels = CONFIG['conda_channels']['main']
    elif conda_channel in CONFIG['conda_channels']:
        conda_channels = CONFIG['conda_channels'][conda_channel]
    else:
        conda_channels = [conda_channel]
    unreachable = []
    for c in conda_channels:
        try:
            requests.get(c.format(**os.environ), timeout=2)
        except KeyError as e:
            # this clears the exception we just caugh and raises another one
            raise Exception('Missing expected environmental variable: {e}'.format(e=str(e))) from None
        except requests.ConnectTimeout:
            c2 = urllib.parse.urlparse(c)
            c2 = urllib.parse.urlunparse((c2.scheme,
                                          c2.netloc.split('@')[-1],
                                          c2.path, c2.params, c2.query, c2.fragment))
            unreachable.append(c2)
        cmd += ['--channel', c.format(**os.environ)]

    if unreachable:
        msg = 'The following conda channels are not reachable:\n -'
        msg += ' -'.join([c for c in unreachable])
        raise NetworkException(msg)

    p = subprocess.run(cmd, **kwargs)
    out = json.loads(p.stdout.decode())
    if 'error' in out and 'exception_name' in out \
            and out['exception_name'] == 'PackagesNotFoundError':
        out = []
    if 'error' in out:
        if 'message' in out:
            raise Exception(out['message'])
        else:
            raise Exception(str(out))
    return out


def get_conda_pkg_dependencies(conda_package,
                               conda_channel=None):
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
        raise Exception('{conda_package} not found.'.format(conda_package=conda_package))
    packages = out[conda_package][-1]['depends']
    packages = dict([(p.split('==')[0].strip(), p.split('==')[1].strip())
                     for p in packages])
    return packages


def _get_release_commit(repository, release_name):
    """
    Quaternion releases 3.4.1 and 3.5.1 give different results
    :param repository:
    :param release_name:
    :return:
    """
    obj = repository.tags(name=release_name)['object']
    if obj['type'] == 'tag':
        obj = repository.tags(tag_sha=obj['sha'])['object']
    if obj['type'] != 'commit':
        raise Exception('Object is not a commit, but a {t}'.format(t=obj["type"]))
    return obj


def _get_repository_info_v3(owner_repo,
                            since=7,
                            use_pr_titles=True,
                            include_unreleased_commits=False,
                            include_commits=False):
    """
    Get information about a Github repository

    :param owner_repo: str
        the name of the repository, including owner, something like 'sot/skare3'.
    :param since: int or str
        the maximum number of releases to look back, or the release tag to look back to
        (not inclusive).
    :param use_pr_titles: bool
        Whether to use PR titles instead of the PR commit message.
        This is so one can change PR titles after the fact to be more informative.
    :param include_unreleased_commits: bool
        whether to include commits and merges for repositories that have no release.
        This affects only top-level entries 'commits', 'merges', 'merge_info'.
        It is for backward compatibility with the dashboard.
    :param include_commits: bool
        whether to include commits in release_info.
    :return:
    """
    github.init()
    api = github.GITHUB_API_V3

    owner, repo = owner_repo.split('/')
    repository = github.Repository(owner_repo)

    releases = [release for release in repository.releases()
                if not release['prerelease'] and not release['draft']]

    # get the actual commit sha and date for each release
    release_commits = [_get_release_commit(repository, r["tag_name"]) for r in releases]
    release_commits = [repository.commits(ref=c['sha']) for c in release_commits]
    release_dates = {r['tag_name']: c['commit']['committer']['date'] for r, c in
                     zip(releases, release_commits)}

    # later on, the releases are referred by commit sha
    releases = {c['sha']: r for r, c in zip(releases, release_commits)}

    date_since = None
    if type(since) is int:
        # only the latest 'since' releases (at most) will be included in summary
        if len(releases) > since:
            date_since = sorted(release_dates.values(), reverse=True)[since]
    elif since in release_dates:
        # only releases _after_ 'since' will be included in summary
        date_since = release_dates[since]
    else:
        raise Exception('Requested repository info with since={since},'.format(since=since) +
                        'which is not and integer and is not one of the known releases' +
                        '({releases})'.format(releases=sorted(release_dates.keys())))

    release_info = [{
        'release_tag': '',
        'release_tag_date': '',
        'commits': [],
        'merges': []
    }]

    if use_pr_titles:
        all_pull_requests = repository.pull_requests(state='all')
        all_pull_requests = {pr['number']: pr for pr in all_pull_requests}
    commits = repository.commits(sha='master', since=date_since)
    if date_since is not None:
        commits = commits[:-1]  # remove first commit, which was just the starting point
    for commit in commits:
        sha = commit['sha']
        if sha in releases.keys():
            release_info.append({
                'release_tag': releases[sha]["tag_name"],
                'release_tag_date': releases[sha]["published_at"],
                'commits': [],
                'merges': []
            })

        release_info[-1]['commits'].append({
            'sha': commit['sha'],
            'message': commit['commit']['message'],
            'date': commit['commit']['committer']['date'],
            'author': commit['commit']['author']['name']
        })
        match = re.match(
            'Merge pull request #(?P<pr_number>.+) from (?P<branch>\S+)\n\n(?P<title>.+)',
            commit['commit']['message'])
        if match:
            merge = match.groupdict()
            merge["pr_number"] = int(merge["pr_number"])
            if use_pr_titles:
                if merge["pr_number"] in all_pull_requests:
                    merge["title"] = all_pull_requests[merge["pr_number"]]['title'].strip()
            release_info[-1]['merges'].append(merge)

    if len(release_info) > 1:
        last_tag = release_info[1]['release_tag']
        last_tag_date = release_info[1]['release_tag_date']
    else:
        last_tag = ''
        last_tag_date = ''

    branches = repository.branches()
    issues = [i for i in repository.issues() if 'pull_request' not in i]

    pull_requests = []
    for pr in repository.pull_requests():
        pr_commits = api.get(pr['commits_url']).json()
        date = pr_commits[-1]['commit']['committer']['date']
        pull_requests.append({'number': pr['number'],
                              'url': pr['_links']['html']['href'],
                              'title': pr['title'],
                              'n_commits': len(pr_commits),
                              'last_commit_date': date})

    headers = {'Accept': 'application/vnd.github.antiope-preview+json'}
    workflows = api.get(
        '/repos/{owner}/{repo}/actions/workflows'.format(owner=owner, repo=repo),
        headers=headers).json()
    workflows = [{k: w[k] for k in ['name', 'badge_url']} for w in workflows['workflows']]

    repo_info = {
        'owner': owner,
        'name': repo,
        'last_tag': last_tag,
        'last_tag_date': last_tag_date,
        'commits': len(release_info[0]['commits']),
        'merges': len(release_info[0]['merges']),
        'merge_info': release_info[0]['merges'],
        'release_info': release_info,
        'issues': len(issues),
        'n_pull_requests': len(pull_requests),
        'branches': len(branches),
        'pull_requests': pull_requests,
        'workflows': workflows
    }

    if not include_commits:
        for r in repo_info['release_info']:
            del r['commits']

    if not include_unreleased_commits and len(repo_info['release_info']) == 1:
        repo_info['commits'] = 0
        repo_info['merges'] = 0
        repo_info['merge_info'] = []

    return repo_info


_LAST_UPDATED_QUERY = jinja2.Template("""
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
""")


def repository_info_is_outdated(_, pkg_info):
    result = github.GITHUB_API_V4(_LAST_UPDATED_QUERY.render(**pkg_info))
    result = result['data']['repository']
    outdated = (pkg_info['pushed_at'] < result['pushedAt'] or
                pkg_info['updated_at'] < result['updatedAt'])
    return outdated


@json_cache('pkg_repository_info',
            directory='pkg_info',
            update_policy=repository_info_is_outdated)
def get_repository_info(owner_repo, version='v4', **kwargs):
    """
    Get information about a Github repository

    :param owner_repo: str
        the name of the repository, including owner, something like 'sot/skare3'.
    :param since: int or str
        the maximum number of releases to look back, or the release tag to look back to
        (not inclusive).
    :param use_pr_titles: bool
        Whether to use PR titles instead of the PR commit message.
        This is so one can change PR titles after the fact to be more informative.
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
    owner, name = owner_repo.split('/')

    if version == 'v4':
        info = _get_repository_info_v4(owner_repo, **kwargs)
    else:
        info = _get_repository_info_v3(owner_repo, **kwargs)

    info['master_version'] = ''
    conda_info = get_conda_pkg_info(name, conda_channel='masters')
    if name.lower() in conda_info:
        info['master_version'] = conda_info[name.lower()][-1]['version']

    return info


def get_repositories_info(repositories=None, version='v4', update=False):
    if repositories is None:
        repositories = [p['repository'] for p in get_package_list()
                        if p['owner'] in CONFIG['organizations']]
    repo_package_map = {p['repository']: p['package'] for p in get_package_list()
                        if p['repository']}

    info = {'packages': []}
    meta_pkg_versions = {pkg: {r: '' for r in repositories}
                         for pkg in ['ska3-flight', 'ska3-matlab']}

    for pkg in ['ska3-flight', 'ska3-matlab']:
        try:
            assert pkg in meta_pkg_versions
            conda_info = get_conda_pkg_info(pkg, conda_channel='main')[pkg][-1]
            info[pkg] = conda_info['version']
            versions = dict([(p.split('==')[0].strip(), p.split('==')[1].strip())
                             for p in conda_info['depends']])
            for owner_repo in repositories:
                assert owner_repo in repo_package_map, 'Package {owner_repo} not in package map'.format(owner_repo=owner_repo)
                conda_pkg = repo_package_map[owner_repo]
                if conda_pkg in versions:
                    assert owner_repo in meta_pkg_versions[pkg]
                    meta_pkg_versions[pkg][owner_repo] = versions[conda_pkg]
        except NetworkException as e:
            logging.error(e)
            raise
        except Exception as e:
            logging.warning('Empty {pkg}: {t}: {e}'.format(pkg=pkg, t=type(e), e=e))

    for owner_repo in repositories:
        # print(owner_repo)
        try:
            repo_info = get_repository_info(owner_repo, version=version, update=update)
            repo_info['matlab'] = meta_pkg_versions['ska3-matlab'][owner_repo]
            repo_info['flight'] = meta_pkg_versions['ska3-flight'][owner_repo]
            info['packages'].append(repo_info)
        except Exception as e:
            logging.warning('Failed to get info on %s: %s', owner_repo, e)
            continue

    info.update({'time': datetime.datetime.now().isoformat()})

    return info


def get_parser():
    description = """
SkaRE3 Github information tool.

This script queries Github and a few other sources to determine the status of all packages.
"""

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-o', default='repository_info.json',
                        help='Output file (default=repository_info.json)')
    parser.add_argument('--token', help='Github token, or name of file that contains token')
    return parser


def main():
    args = get_parser().parse_args()

    github.init(token=args.token)

    info = get_repositories_info()
    if info:
        with open(args.o, 'w') as f:
            json.dump(info, f, indent=2)


if __name__ == '__main__':
    main()
