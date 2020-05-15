#!/usr/bin/env python3
"""
Produce a list of changes for all packages between two sets of versions.

The sets of versions can be specified in a few ways: 1. one string of flight, matlab, last_tag,
2. one string that must correspond to a package in conda-info file 3. the name of a json file
containing a dictionary of versions indexed by package names (which can be created doing
"conda search --info --json ska3-flight", for example).

The changes come from a json file created with skare3-github-info.

This script requires a "name map" JSON file, which contains a list of dictionaries, one per package.
Each dictionary lists the different names by which this package is known (pyton module, github repo,
conda package). This is to merge information from conda and github.
"""
import os
import json
import argparse
import logging
import collections


class ArgumentException(Exception):
    pass


def repository_change_summary(packages, initial_versions='flight', final_versions='last_tag'):
    """
    Assemble a list of all PR merges that occured between initial_version and final_version.

    :param packages:
        dictionary with github repository information
    :param initial_versions: str or dict
        if this is a string, it must be one of 'flight', 'matlab', 'last_tag'
        if this is a dictionary, it must me of the form {name: version}
    :param final_versions:  str or dict
        if this is a string, it must be one of 'flight', 'matlab', 'last_tag'
        if this is a dictionary, it must me of the form {name: version}
    :return:
    """
    packages = packages.copy()
    for p in packages:
        p['full_name'] = f"{p['owner']}/{p['name']}"

    summary = []
    packages = [p for p in packages
                if p['full_name'] in final_versions and p['full_name'] in initial_versions
                and final_versions[p['full_name']]]
    for p in packages:
        p.update({'version_1': initial_versions[p['full_name']],
                  'version_2': final_versions[p['full_name']]})
        if p['version_2'] != p['version_1']:
            releases = [r['release_tag'] for r in p['release_info']]
            if p['version_1'] not in releases:
                logging.warning(f" - Initial version of {p['full_name']} is not in release list:"
                                f" {p['version_1']}, {releases}")
            if len(releases) == 1 and releases[0] == '':
                logging.warning(f'Package {p["name"]} has no releases?')
                continue

            if p['version_1'] in releases and p['version_1']:
                releases = releases[releases.index(p['version_2']):releases.index(p['version_1'])]
            else:
                releases = releases[releases.index(p['version_2']):]
            release_info = {r['release_tag']: r['merges'] for r in p['release_info']}
            merges = []
            for merge in sum([release_info[k] for k in releases], []):
                pr = merge['pr_number']
                url = f'{p["owner"]}/{p["name"]}/pull/{pr}' if merge['pr_number'] else ''
                merges.append({
                    'PR': pr,
                    'url': url,
                    'description': merge['title']
                })
            summary.append({
                'name': p['full_name'],
                'version_2': p['version_2'],
                'version_1': p['version_1'],
                'versions': [p['version_1']] + releases[::-1],
                'merges': merges[::-1]
            })
    summary = sorted(summary, key=lambda pkg: pkg['name'].lower())
    return summary


def write_conda_pkg_change_summary(change_summary):
    """
    Write conda package change summary in markdown format

    :param change_summary: dict
        the summary
    :return:
    """
    for p in change_summary:
        print('**{name}: {version_1} -> {version_2}**'.format(**p),
              f'({" -> ".join(p["versions"])})')
        for merge in p['merges']:
            print('  - [PR {PR}](https://github.com/{url}): {description}'.format(**merge))
        print('')


# an alternative using jinja2
PKG_SUMMARY_MD = """
{% for package in summary -%}
**{{ package.name }}:** {{ package.version_1 }} -> {{ package.version_2 }} (
{%- for v in package.versions -%}
{{ v }}{{ " -> " if not loop.last }}
{%- endfor %})
{% for merge in package.merges -%}
  - [PR {{ merge.PR }}](https://github.com/{{ merge.url }}): {{ merge.description }}
{% endfor %}
{% endfor %}
"""


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('--initial-version', default='flight',
                       help='Either a string or a json file with dictionary of package/versions.')
    parse.add_argument('--final-version', default='last_tag',
                       help='Either a string or a json file with dictionary of package/versions.')
    parse.add_argument('--repository-info', default='repository_info.json',
                       help='json file output from skare3-github-info')
    parse.add_argument('--conda-info', default=None,
                       help='json file output from "conda search --info --json <package>"')
    parse.add_argument('--pkg-name-map', help='Name of a file with a list of dictionaries')
    return parse


def _get_conda_info(conda_info=None):
    if conda_info:
        with open(conda_info, 'r') as f:
            conda_info = json.load(f)
            conda_packages = list(conda_info.keys())
            conda_info = conda_info[conda_packages[0]]
            conda_info = collections.OrderedDict([(i['version'], i) for i in conda_info])

            for version in conda_info:
                depends = [v.split('==') for v in conda_info[version]['depends']]
                depends = {v[0].strip(): v[1].strip() for v in depends}
                conda_info[version]['depends'] = depends
    else:
        conda_info = {}
    return conda_info


def _get_versions(version, repository_info, conda_info):
    versions = ['flight', 'matlab', 'last_tag']
    if version in conda_info:
        version = conda_info[version]['depends']
    elif version in versions:
        version = {p['full_name']: p[version] for p in repository_info if version in p}
    elif os.path.exists(version):
        with open(version, 'r') as f:
            version = json.load(f)
    else:
        keys = "\n   - " + "\n   - ".join(conda_info.keys())
        versions = "\n   - " + "\n   - ".join(versions)
        msg = (f'Unknown version {version}:\n'
               f' - It is not an existing file name\n'
               f' - It is not one of: {versions}\n'
               )
        if conda_info:
            msg += f' - It is not any of the known versions in conda info: {keys}\n'
        raise Exception(msg)
    return version


def main():
    parse = parser()
    args = parse.parse_args()
    try:
        # assemble dictionaries to get the conda package name from a repo name and vice-versa
        # (conda info only has conda package names, while repository_info only has github repo names)
        repo_to_package = None
        package_to_repo = None
        if args.pkg_name_map:
            with open(args.pkg_name_map, 'r') as f:
                pkg_name_map = json.load(f)
            repo_to_package = {n['repo']: n['package'] for n in pkg_name_map}
            package_to_repo = {n['package']: n['repo'] for n in pkg_name_map}

        with open(args.repository_info) as f:
            repository_info = json.load(f)

        conda_info = _get_conda_info(args.conda_info)

        # change names in conda_info to repository names
        for version in conda_info:
            conda_info[version]['depends'] = {package_to_repo[k]: v
                                              for k, v in conda_info[version]['depends'].items()
                                              if k in package_to_repo}

        # get the version sets (they can come from file, from repository_info or conda_info)
        initial_version = _get_versions(args.initial_version, repository_info, conda_info)

        final_version = _get_versions(args.final_version, repository_info, conda_info)

        change_summary = repository_change_summary(repository_info['packages'],
                                                   initial_versions=initial_version,
                                                   final_versions=final_version)

        # change the name so the one reported is the conda package name and not the repository
        for p in change_summary:
            if p['name'] not in pkg_name_map:
                continue
            p['name'] = repo_to_package[p['name']]

        write_conda_pkg_change_summary(change_summary)
    except ArgumentException as e:
        parse.exit(1, str(e))


if __name__ == '__main__':
    main()
