#!/usr/bin/env python3
"""
Produce a list of changes for meta-packages between versions.

The sets of versions can be specified in a few ways: 1. one string of flight, matlab, last_tag,
2. one string that must correspond to a package in conda-info file 3. the name of a json file
containing a dictionary of versions indexed by package names (which can be created doing
"conda search --info --json ska3-flight", for example).

This script requires CONDA_PASSWORD to be defined.
"""
import os
import json
import argparse
import logging
import collections
from packaging.version import Version
from skare3_tools import packages, github


class ArgumentException(Exception):
    pass


class CondaException(Exception):
    def __init__(self, info):
        super().__init__(info['message'])
        self.info = info


def repository_change_summary(pkgs_repo_info, initial_versions={}, final_versions={}):
    """
    Assemble a list of all PR merges that occurred between initial_version and final_version,
    according to the information contained in pkgs_repo_info.

    The initial_versions and final_versions arguments are dicts with package names and versions,
    like:

        {'ska_helpers': '0.1.1', 'Quaternion': ''}

    The pkgs_repo_info argument must contain information on all releases and PRs for the packages
    in initial_versions and final_versions. This is a typical call of the function:

        pkgs = [packages.get_repository_info('sot/ska_helpers')]
        summary = repository_change_summary(
            pkgs, {'ska_helpers': '0.1.1'}, {'ska_helpers': '0.1.2'}
        )

    :param pkgs_repo_info: list
        List with github repository information. This is usually the result of calling
        :any:`get_repository_info <skare3_tools.packages.get_repository_info>` or the 'packages'
        entry from :any:`get_repositories_info <skare3_tools.packages.get_repositories_info>`.
    :param initial_versions: dict
        Dictionary of the form {name: version}
    :param final_versions: dict
        Dictionary of the form {name: version}
    :return: dict
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
        elif package_name not in final_versions:
            summary['removed'].append(package_name)
        else:
            version_1 = initial_versions[package_name]
            version_2 = final_versions[package_name]
            if version_2 and version_2 != version_1:
                update_info = {
                    'name': package_name,
                    'version_2': version_2,
                    'version_1': version_1,
                }
                if package_name in package_to_repo:
                    full_name = package_to_repo[package_name]
                    if full_name in pkgs_repo_info:
                        p = pkgs_repo_info[full_name]
                        releases = [_clean_version(r['release_tag']) for r in p['release_info']]
                        if version_1 not in releases:
                            # The default repository info looks back a limited number of releases.
                            # If a version is missing, request a larger history
                            # This is a hack, but the default works 99% of the time and is faster.
                            p = packages.get_repository_info(full_name, since=100)
                            releases = [_clean_version(r['release_tag']) for r in p['release_info']]
                        if version_1 not in releases:
                            logging.warning(
                                f" - Initial version of {full_name} is not in release list:"
                                f" {version_1}, {releases}"
                            )
                        if len(releases) == 1 and releases[0] == '':
                            logging.warning(f'Package {p["name"]} has no releases?')
                            continue

                        if version_1 in releases and version_1:
                            releases = releases[releases.index(version_2):releases.index(version_1)]
                        else:
                            releases = releases[releases.index(version_2):]
                        release_info = {
                            _clean_version(r['release_tag']): r['merges'] for r in p['release_info']
                        }
                        merges = []
                        for merge in sum([release_info[k] for k in releases], []):
                            pr = merge['pr_number']
                            if merge['pr_number']:
                                url = f'{p["owner"]}/{p["name"]}/pull/{pr}'
                            else:
                                url = ''
                            merges.append({
                                'PR': pr,
                                'url': url,
                                'description': merge['title'],
                                'author': merge['author']
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


def _clean_version(version):
    """
    Sanitize a version string.

    One of the useful things it does is to change 'v1.0.0' into '1.0.0'.
    """
    if version == '':
        return ''
    return str(Version(version))


def write_conda_pkg_change_summary(change_summary):
    """
    Write conda package change summary in markdown format

    This is a typical use of this function::

        pkgs = [packages.get_repository_info('sot/ska_helpers')]
        summary = repository_change_summary(
            pkgs, {'ska_helpers': '0.1.0'}, {'ska_helpers': '0.1.2'}
        )
        skare3_update_summary.write_conda_pkg_change_summary(summary)

    :param change_summary: dict
        the summary returned by :any:`repository_change_summary`.
    :return:
    """
    import jinja2
    template = jinja2.Template(PKG_SUMMARY_MD)
    print(template.render(summary=change_summary))


"""
# a typical summary looks like this:
summary = {
    'final_version': '2022.6',
    'initial_version': '2022.2',
    'new': [{'name': 'dataclasses', 'version': '0.8', 'dummy': 1.0}],
    'package': 'ska3-core',
    'removed': ['sherpa', 'another'],
    'updates': [
        {'name': 'black', 'version_1': '19.10b0', 'version_2': '22.3.0'},
        {'name': 'pathspec', 'version_1': '0.7.0', 'version_2': '0.9.0'}
    ]
}
"""


PKG_SUMMARY_MD = """
## {{ summary.package }} changes ({{ summary.initial_version }} -> {{ summary.final_version }})

{% if summary.new|length > 0 -%}### New Packages

{% for package in summary.new -%}
- **{{ package.name }}: {{ package.version }}**
{% endfor %}
{% endif -%}
{% if 'removed' in summary and summary.removed|length > 0 -%}
### Removed Packages

{% for package in summary.removed -%}
- **{{ package }}**
{% endfor %}
{% endif -%}
{% if 'updates' in summary and summary.updates|length > 0 -%}
### Updated Packages

{% for package in summary.updates -%}
- **{{ package.name }}:** {{ package.version_1 }} -> {{ package.version_2 }}
{%- if 'versions' in package %} ({% for v in package.versions -%}
{{ v }}{{ " -> " if not loop.last }}
{%- endfor %}){% endif %}
{%-  for mrg in package.merges %}
  - [PR {{ mrg.PR }}](https://github.com/{{ mrg.url }}) ({{ mrg.author }}): {{ mrg.description }}
{%- endfor %}
{% endfor %}
{% endif -%}
"""


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument(
        '--initial-version', default=None,
        help='A string id. The default is the last non-prerelease version.'
    )
    parse.add_argument(
        '--final-version', default=None,
        help='A string id. The default is the last version.'
    )
    parse.add_argument(
        '--meta-package', default=[], action='append',
        help='Name of the meta-package. Default is all meta-packages at the given final version.'
    )
    parse.add_argument(
        '--conda-channel',
        default='test',
        help=(
            'Conda channel where info for the final version of the meta-package can be found.'
            'The default is to use the test channel.'
        )
    )
    parse.add_argument('--token', help='Github token, or name of file that contains token')
    return parse


def _get_versions(version, repository_info, conda_info):
    """
    Get a dictionary of package names and versions corresponding to the given `version`.

    conda_info is a dictionary like this:
        {'2021.1': {'depends': [...], ...}, '2021.2': {'depends': [...], ...}, ...}
    this ultimately comes from making a call like
        conda search ska3-flight --json

    repository_info is a list, where each entry is the result of calling
    :any:`get_repository_info <skare3_tools.packages.get_repository_info>`. These have
    three special keys ('last_tag', 'flight', 'matlab') which list the latest release,
    and the version of the package currently in ska3-flight or ska3-matlab respectively.

    the version has to be one of the following:
    - a key in conda_info
    - in ['flight', 'matlab', 'last_tag']
    - a json file

    for a package to be included in the result, it must have an associated package name given by
    :any:`get_package_list <skare3_tools.packages.get_package_list>`. This is trivially the case
    if version is 'flight' or 'matlab', but not if version is 'last_tag'.

    This will return all the package versions in ska3-flight:

        repository_info = packages.get_repositories_info()
        skare3_update_summary._get_versions('flight', repository_info['packages'], {})

    This will return all the package versions in ska3-matlab:

        repository_info = packages.get_repositories_info()
        skare3_update_summary._get_versions('matlab', repository_info['packages'], {})

    This will return all the package versions corresponding to their last tag:

        repository_info = packages.get_repositories_info()
        skare3_update_summary._get_versions('last_tag', repository_info['packages'], {})



    returns a dict {name: version}
    """
    pkg_name_map = packages.get_package_list()
    repo_to_package = {
        n['repository']: n['package'] for n in pkg_name_map if n['repository'] and n['package']
    }

    special_versions = ['flight', 'matlab', 'last_tag']
    if version in conda_info:
        version = conda_info[version]['depends']
    elif version in special_versions:
        version = {
            repo_to_package[f'{p["owner"]}/{p["name"]}']: p[version]
            for p in repository_info
            if version in p and p[version] and f'{p["owner"]}/{p["name"]}' in repo_to_package
        }
    elif os.path.exists(version):
        with open(version, 'r') as f:
            version = json.load(f)
    else:
        keys = "\n   - " + "\n   - ".join(conda_info.keys())
        special_versions = "\n   - " + "\n   - ".join(special_versions)
        msg = (f'Unknown version {version}:\n'
               f' - It is not an existing file name\n'
               f' - It is not one of: {special_versions}\n'
               )
        if conda_info:
            msg += f' - It is not any of the known versions in conda info: {keys}\n'
        raise Exception(msg)
    return version


def changes(meta_package, initial_version, final_version, conda_channel):
    """
    Write a change summary between two versions of a meta-package (a list of PRs for each package).

    Example:

        from skare3_tools.scripts import skare3_update_summary
        skare3_update_summary.changes('ska3-flight', '2022.6', '2022.7rc4', 'test')

    """
    repository_info = packages.get_repositories_info()

    conda_info = packages.get_conda_pkg_info(meta_package,
                                             conda_channel=conda_channel)
    conda_info = collections.OrderedDict(
        [(i['version'], i) for i in conda_info[meta_package]]
    )

    # get the version sets (they can come from file, from repository_info or conda_info)
    initial_versions = _get_versions(initial_version, repository_info, conda_info)

    final_versions = _get_versions(final_version, repository_info, conda_info)

    change_summary = repository_change_summary(
        repository_info['packages'],
        initial_versions=initial_versions,
        final_versions=final_versions
    )
    change_summary.update({
        'package': meta_package,
        'initial_version': initial_version,
        'final_version': final_version,
    })

    write_conda_pkg_change_summary(change_summary)


def process_args(args):
    import subprocess
    import json

    if 'CONDA_PASSWORD' not in os.environ:
        raise ArgumentException('CONDA_PASSWORD environmental variable is not defined')
    CONDA_PASSWORD = os.environ['CONDA_PASSWORD']

    # First, get all versions of ska3-* packages in the conda channel
    channel = sum(
        [['-c', c.format(CONDA_PASSWORD=CONDA_PASSWORD)]
         for c in packages.CONFIG['conda_channels'][args.conda_channel]],
        []
    )
    p = subprocess.run(
        ['conda', 'search', '--json'] + channel + ['ska3-'], stdout=subprocess.PIPE
    )
    info = json.loads(p.stdout.decode())
    if "error" in info:
        raise CondaException(info)

    versions = {name: sorted([Version(p['version']) for p in info[name]]) for name in info}
    meta_package = args.meta_package
    if not meta_package and args.final_version:
        meta_package = [
            name for name in versions if Version(args.final_version) in versions[name]
        ]

    # iterate over meta-packages, potentially finding the initial version for each
    result = []
    for name in meta_package:
        # Set the default values for arguments
        initial_version = args.initial_version
        final_version = args.final_version

        if not final_version and meta_package:
            final_version = str(versions[name][-1])
        if initial_version is None:
            release_versions = [
                str(version) for version in versions[name] if version < Version(final_version)
                and not version.is_devrelease and not version.is_prerelease
            ]
            if not release_versions:
                continue
            initial_version = release_versions[-1]

        def check_version(version):
            known_versions = [str(s) for s in versions[name]]
            if version not in known_versions:
                known_versions_str = "- " + "\n- ".join(known_versions)
                raise ArgumentException(
                    f'Unknown {name} version {version}. Known versions:\n{known_versions_str}'
                )

        check_version(initial_version)
        check_version(final_version)

        result.append({
            'initial_version': initial_version,
            'final_version': final_version,
            'meta_package': name,
            'conda_channel': args.conda_channel,
        })

    return result


def main():
    parse = parser()
    args = parse.parse_args()

    if not args.final_version and not args.meta_package:
        parse.error('At least --final-version or --meta-package need to be given')

    github.init(token=args.token)

    try:
        args_2 = process_args(args)
        for a in args_2:
            changes(**a)
    except ArgumentException as e:
        parse.exit(1, f'{e}\n')
    except CondaException as e:
        parse.exit(1, f'Error running conda:\n{e}\n')


if __name__ == '__main__':
    main()
