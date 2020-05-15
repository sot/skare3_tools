#!/usr/bin/env python3
"""
SkaRE3 Github information tool.

This script queries Github and a few other sources to determine the status of all packages.
NOTE: Running within ska3-flight or ska3-matlab will cause errors that produce wrong results.
"""

from skare3_tools import github
import sys
import os
import re
import json
import argparse
import subprocess
import logging
import datetime
import yaml


REPO_PACKAGE_MAP = [
    ('eng_archive', 'ska.engarchive'),
    ('cmd_states', 'chandra.cmd_states')
]


def get_repositories_info_v4(owner):
    """
    This should do something very similar to get_repositories_info but much faster.
    It uses the GraphQL interface (v4) instead of the REST interface (v3)

    :param owner: str
        the Github organization (e.g. 'sot' or 'acisops')
    :return:
    """
    import jinja2
    from skare3_tools.github import graphql
    api = graphql.init()
    query = jinja2.Template(graphql.ORG_QUERY).render(owner=owner)
    repositories = api(query)['data']['organization']['repositories']
    # note that in the following step I am not iterating over pages, which is oversimplifying things
    repositories = [(r['owner']['login'], r['name']) for r in repositories['nodes']]
    data = []
    for owner, name in repositories:
        print(f'{owner}/{name}')
        data.append(api(jinja2.Template(graphql.REPO_QUERY).render(name=name, owner=owner)))

    return data


def get_conda_pkg_versions_2(conda_metapackage):
    out = subprocess.check_output(['conda', 'install', conda_metapackage, '--dry-run']).decode()
    out = out[out.find('The following NEW packages will be INSTALLED:'):
              out.find('The following packages will be UPDATED')].split('\n')
    packages = [p.split() for p in out if p and p[0] == ' ']
    packages = {p[0][:-1]: p[1] for p in packages}
    for k, v in packages.items():
        m = re.match('(?P<version>\S+)(-py[0-9]*_[0-9]+)', v)
        if m:
            packages[k] = m.groupdict()['version']
    return packages


def get_conda_pkg_info(conda_package,
                       conda_channel='https://icxc.cfa.harvard.edu/aspect/ska3-conda'):
    if sys.version_info.major == 3 and sys.version_info.minor >= 7:
        kwargs = {'capture_output': True}
    else:
        kwargs = {'stdout': subprocess.PIPE}
    p = subprocess.run(['conda', 'search', conda_package, '--channel', conda_channel, '--json'],
                       **kwargs
                       )
    out = json.loads(p.stdout.decode())
    return out


def get_conda_pkg_dependencies(
        conda_metapackage,
        conda_channel='https://icxc.cfa.harvard.edu/aspect/ska3-conda'):
    out = get_conda_pkg_info(conda_metapackage, conda_channel)
    if conda_metapackage not in out:
        raise Exception(f'{conda_metapackage} not found.')
    packages = out[conda_metapackage][-1]['depends']
    packages = dict([(p.split('==')[0].strip(), p.split('==')[1].strip())
                     for p in packages])
    return packages


def get_release_commit(repository, release_name):
    """
    Quaternion releases 3.4.1 and 3.5.1 give different results
    :param repository:
    :param release_name:
    :return:
    """
    object = repository.tags(name=release_name)['object']
    if object['type'] == 'tag':
        object = repository.tags(tag_sha=object['sha'])['object']
    if object['type'] != 'commit':
        raise Exception(f'Object is not a commit, but a {object["type"]}')
    return object


def get_repository_info(owner_repo, since=7,
                        use_pr_titles=True,
                        include_unreleased_commits=False, include_commits=False):
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
    api = github.init()
    owner, repo = owner_repo.split('/')
    repository = github.Repository(owner_repo)

    releases = [release for release in repository.releases()
                if not release['prerelease'] and not release['draft']]

    # get the actual commit sha and date for each release
    release_commits = [get_release_commit(repository, r["tag_name"]) for r in releases]
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
        raise Exception(f'Requested repository info with since={since},'
                        f'which is not and integer and is not one of the known releases'
                        f'({sorted(release_dates.keys())})')

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
    workflows = api.get(f'/repos/{owner}/{repo}/actions/workflows', headers=headers).json()
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


def get_repositories_info(repositories, conda=True):
    matlab = {}
    flight = {}
    info = {'packages': []}
    if conda:
        try:
            flight = get_conda_pkg_dependencies('ska3-flight')
            info['ska3-flight'] = get_conda_pkg_info('ska3-flight')['ska3-flight'][-1]['version']
            for repo, conda_pkg in REPO_PACKAGE_MAP:
                if conda_pkg in flight:
                    flight[repo] = flight[conda_pkg]
        except Exception as e:
            logging.warning(f'Empty ska3-flight: {type(e)}: {e}')
        try:
            matlab = get_conda_pkg_dependencies('ska3-matlab')
            info['ska3-matlab'] = get_conda_pkg_info('ska3-matlab')['ska3-matlab'][-1]['version']
            for repo, conda_pkg in REPO_PACKAGE_MAP:
                if conda_pkg in matlab:
                    matlab[repo] = matlab[conda_pkg]
        except Exception as e:
            logging.warning(f'Empty ska3-matlab: {type(e)}: {e}')
    for owner_repo in repositories:
        print(owner_repo)
        try:
            owner, repo = os.path.split(owner_repo)
            repo_info = get_repository_info(owner_repo)
            repo_info['matlab'] = matlab[repo.lower()] if repo.lower() in matlab else ''
            repo_info['flight'] = flight[repo.lower()] if repo.lower() in flight else ''
            info['packages'].append(repo_info)
        except Exception as e:
            print(f'{type(e)}: {e}')

        repo_info['dev'] = ''
        if conda:
            dev_info = get_conda_pkg_info(
                repo, 'https://ska:ska-cxc-20y@cxc.cfa.harvard.edu/mta/ASPECT/ska3-conda/dev')
            if repo.lower() in dev_info:
                repo_info['dev'] = dev_info[repo.lower()][-1]['version']

    info.update({'time': datetime.datetime.now().isoformat()})

    return info


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-o', default='repository_info.json',
                        help='Output file (default=repository_info.json)')
    parser.add_argument('-u', help='User name')
    parser.add_argument('-c', help='Netrc file name with credentials')
    return parser


def main():
    args = get_parser().parse_args()

    if args.c:
        with open(args.c) as f:
            data = yaml.load(f)
            github.init(user=data['user'], password=data['password'])
    else:
        github.init(user=args.u)

    orgs = [github.Organization('sot'),
            github.Organization('acisops'),
            ]
    repositories = sorted([r['full_name'] for org in orgs for r in org.repositories()])
    info = get_repositories_info(repositories)
    if info:
        with open(args.o, 'w') as f:
            json.dump(info, f, indent=2)


if __name__ == '__main__':
    main()
