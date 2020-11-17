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
from skare3_tools import packages, github


class ArgumentException(Exception):
    pass


def repository_change_summary(pkgs_repo_info, initial_versions='flight', final_versions='last_tag'):
    """
    Assemble a list of all PR merges that occurred between initial_version and final_version.

    :param pkgs_repo_info:
        dictionary with github repository information
    :param initial_versions: str or dict
        if this is a string, it must be one of 'flight', 'matlab', 'last_tag'
        if this is a dictionary, it must me of the form {name: version}
    :param final_versions:  str or dict
        if this is a string, it must be one of 'flight', 'matlab', 'last_tag'
        if this is a dictionary, it must me of the form {name: version}
    :return:
    """
    pkg_name_map = packages.get_package_list()
    package_to_repo = {n['package']: n['repository'] for n in pkg_name_map
                       if n['repository'] and n['package']}

    pkgs_repo_info = {f"{p['owner']}/{p['name']}": p for p in pkgs_repo_info}
    summary = {'updates': [], 'new': [], 'removed': []}
    package_names = sorted(set(list(final_versions) + list(initial_versions)))
    for package_name in package_names:
        if package_name not in initial_versions:
            summary['new'].append(
                {'name': package_name, 'version': final_versions[package_name]}
            )
        elif package_name not in final_versions or not final_versions[package_name]:
            summary['removed'].append(package_name)
        else:
            version_1 = initial_versions[package_name]
            version_2 = final_versions[package_name]
            if version_2 != version_1:
                update_info = {
                    'name': package_name,
                    'version_2': version_2,
                    'version_1': version_1,
                }
                if package_name in package_to_repo:
                    full_name = package_to_repo[package_name]
                    if full_name in pkgs_repo_info:
                        p = pkgs_repo_info[full_name]
                        releases = [r['release_tag'] for r in p['release_info']]
                        if version_1 not in releases:
                            logging.warning(f" - Initial version of {full_name} is not in release list:"
                                            f" {version_1}, {releases}")
                        if len(releases) == 1 and releases[0] == '':
                            logging.warning(f'Package {p["name"]} has no releases?')
                            continue

                        if version_1 in releases and version_1:
                            releases = releases[releases.index(version_2):releases.index(version_1)]
                        else:
                            releases = releases[releases.index(version_2):]
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
                        update_info.update({
                            'versions': [version_1] + releases[::-1],
                            'merges': merges[::-1]
                        })
                summary['updates'].append(update_info)

    summary['removed'] = sorted(summary['removed'])
    summary['new'] = sorted(summary['new'], key=lambda pkg: pkg['name'].lower())
    summary['updates'] = sorted(summary['updates'], key=lambda pkg: pkg['name'].lower())

    return summary


def write_conda_pkg_change_summary(change_summary):
    """
    Write conda package change summary in markdown format

    :param change_summary: dict
        the summary
    :return:
    """
    import jinja2
    template = jinja2.Template(PKG_SUMMARY_MD)
    print(template.render(summary=change_summary))


# an alternative using jinja2
PKG_SUMMARY_MD = """
## {{ summary.package }} changes ({{ summary.initial_version }} -> {{ summary.final_version }})

{%if 'new' in summary %}### New Packages{% endif %}
{% for package in summary.new -%}
- **{{ package.name }}: {{ package.version }}**
{% endfor %}

{% if 'removed' in summary and summary.removed|length > 0 %}### Removed Packages{% endif %}
{% for package in summary.removed %}
- **{{ package }}**
{%- endfor %}

### Updated Packages

{% for package in summary.updates -%}
- **{{ package.name }}:** {{ package.version_1 }} -> {{ package.version_2 }}
{%- if 'versions' in package %} ({% for v in package.versions -%}
{{ v }}{{ " -> " if not loop.last }}
{%- endfor %}){% endif %}
{%-  for merge in package.merges %}
  - [PR {{ merge.PR }}](https://github.com/{{ merge.url }}): {{ merge.description }}
{%- endfor %}
{% endfor %}
"""


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('--initial-version', default='flight',
                       help='Either a string or a json file with dictionary of package/versions.')
    parse.add_argument('--final-version', default='last_tag',
                       help='Either a string or a json file with dictionary of package/versions.')
    parse.add_argument('--meta-package', default='ska3-flight')
    parse.add_argument('--conda-channel', action='append', default=[])
    parse.add_argument('--token', help='Github token, or name of file that contains token')
    return parse


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


def split_versions(depends):
    result = {}
    for depend in depends:
        v = depend.split('==') if '==' in depend else depend.split()
        if len(v) > 2:
            raise Exception(f'Version spec got split into too many parts: {depend}')
        p_name = v[0].strip()
        p_version = v[1].strip() if len(v) == 2 else '---'
        result[p_name] = p_version
    return result


def main():
    parse = parser()
    args = parse.parse_args()

    if len(args.conda_channel) == 0:
        args.conda_channel = 'test'
    elif len(args.conda_channel) == 1:
        args.conda_channel = args.conda_channel[0]

    github.init(token=args.token)

    try:

        repository_info = packages.get_repositories_info()

        conda_info = packages.get_conda_pkg_info(args.meta_package,
                                                 conda_channel=args.conda_channel)
        conda_info = collections.OrderedDict(
            [(i['version'], i) for i in conda_info[args.meta_package]]
        )
        for version in conda_info:
            conda_info[version]['depends'] = split_versions(conda_info[version]['depends'])

        # get the version sets (they can come from file, from repository_info or conda_info)
        initial_version = _get_versions(args.initial_version, repository_info, conda_info)

        final_version = _get_versions(args.final_version, repository_info, conda_info)

        change_summary = repository_change_summary(repository_info['packages'],
                                                                  initial_versions=initial_version,
                                                                  final_versions=final_version)
        change_summary.update({
            'package': args.meta_package,
            'initial_version': args.initial_version,
            'final_version': args.final_version,
        })

        write_conda_pkg_change_summary(change_summary)
    except ArgumentException as e:
        parse.exit(1, str(e))


if __name__ == '__main__':
    main()
