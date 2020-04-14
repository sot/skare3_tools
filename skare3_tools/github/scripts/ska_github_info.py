#!/usr/bin/env python3
"""
SkaRE3 Github information tool.

This script queries Github and a few other sources to determine the status of all packages.
NOTE: Running within ska3-flight or ska3-matlab will cause errors that produce wrong results.
"""

from skare3_tools import github
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
    out = subprocess.check_output(
        ['conda', 'search', conda_package, '--channel', conda_channel, '--json']).decode()
    out = json.loads(out)
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


def get_repository_info(owner_repo):
    api = github.init()
    owner, repo = owner_repo.split('/')
    repository = github.Repository(owner_repo)

    last_tag = api.get(f'repos/{owner}/{repo}/releases/latest').json()
    if "tag_name" in last_tag:
        tag_info = api.get(f'repos/{owner}/{repo}/git/ref/tags/{last_tag["tag_name"]}').json()
        tag_sha = tag_info['object']['sha']
        rel_commit = api.get(f'repos/{owner}/{repo}/commits/{tag_sha}').json()
        commit_date = rel_commit['commit']['author']['date']

        commits = api.get(f'repos/{owner}/{repo}/commits',
                          params={'sha': 'master', 'since': commit_date}).json()
        commits = commits[:-1]  # remove the commit associated to the release

        merges = []
        for commit in commits:
            msg = commit['commit']['message']
            match = re.match(
                'Merge pull request (?P<pr>.+) from (?P<branch>\S+)\n\n(?P<description>.+)', msg)
            if match:
                msg = match.groupdict()
                merges.append(f'PR{msg["pr"]}: {msg["description"]}')
    else:
        last_tag = {'tag_name': '', 'published_at': ''}
        commits = []
        merges = []
    branches = api.get(f'repos/{owner}/{repo}/branches').json()
    n_branches = len(branches)
    n_commits = len(commits)

    issue_page = api.get(f'repos/{owner}/{repo}/issues', params={'per_page': 100}).json()
    issues = issue_page
    while len(issue_page) == 100:
        issue_page = api.get(f'repos/{owner}/{repo}/issues', params={'per_page': 100}).json()
        issues += issue_page
    n_pr = len([i for i in issues if 'pull_request' in i])
    n_issues = len(issues) - n_pr

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
        'last_tag': last_tag["tag_name"],
        'last_tag_date': last_tag['published_at'],
        'commits': n_commits,
        'merges': len(merges),
        'merge_info': merges,
        'issues': n_issues,
        'n_pull_requests': n_pr,
        'branches': n_branches,
        'pull_requests': pull_requests,
        'workflows': workflows
    }
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


    info.update({'time': datetime.datetime.now().isoformat()
                 })

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
    """
    repositories = [
        'sot/Chandra.Maneuver',
        'sot/Chandra.Time',
        'sot/Quaternion',
        'sot/Ska.DBI',
        'sot/Ska.File',
        'sot/Ska.Matplotlib',
        'sot/Ska.Numpy',
        'sot/Ska.ParseCM',
        'sot/Ska.Shell',
        'sot/Ska.Sun',
        'sot/Ska.arc5gl',
        'sot/Ska.astro',
        'sot/Ska.ftp',
        'sot/Ska.quatutil',
        'sot/Ska.tdb',
        'sot/acdc',
        'sot/acis_taco',
        'sot/agasc',
        'sot/annie',
        'sot/chandra_aca',
        'sot/cmd_states',
        'sot/cxotime',
        'sot/eng_archive',
        'sot/hopper',
        'sot/kadi',
        'sot/maude',
        'sot/mica',
        'sot/parse_cm',
        'sot/proseco',
        'sot/pyyaks',
        'sot/ska_path',
        'sot/ska_sync',
        'sot/sparkles',
        'sot/starcheck',
        'sot/tables3_api',
        'sot/testr',
        'sot/xija'
    ])
    """
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
