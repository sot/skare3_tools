#!/usr/bin/env python
"""
Script to wrap the standard skare3 building script.

This script differs in a few ways from the standard build:

* The input is a github repository, and the corresponding conda package name is inferred.
* The package version of some conda packages can be overwritten. This is used when building a
  release candidate (with an added 'rc' at the end of the version) without modifying meta.yml.
* Replace CONDA_PASSWORD in conda channel URLs on the fly (older conda versions failed to do this)
* ensure there are non-empty directories linux-64, osx-64, noarch, and win-64 in the output

**WARNING** This script has the side effect of setting git's global username and email.
"""
import sys
import os
import subprocess
import glob
import shutil
import jinja2
import yaml
import re
from string import Template
from packaging import version
import argparse
import tempfile

def overwrite_skare3_version(current_version, new_version, skare3_path,
                             meta_pkgs = ['ska3-flight', 'ska3-matlab', 'ska3-core']):
    for pkg in meta_pkgs:
        meta_file = os.path.join(skare3_path, 'pkg_defs', pkg, 'meta.yaml')
        t = jinja2.Template(open(
            meta_file
        ).read())
        text = (t.render(SKA_PKG_VERSION='$SKA_PKG_VERSION',
                         SKA_TOP_SRC_DIR='$SKA_TOP_SRC_DIR'))
        if version.parse(yaml.__version__) < version.parse("5.1"):
            data = yaml.load(text)
        else:
            data = yaml.load(text, Loader=yaml.FullLoader)
        if str(data['package']['version']) != str(current_version):
            continue
        data['package']['version'] = new_version
        for i in range(len(data['package']['requirements'])):
            if re.search('==', data['package']['requirements']['run'][i]):
                name, pkg_version = data['package']['requirements']['run'][i].split('==')
                name = name.strip()
                if name in meta_pkgs and pkg_version == current_version:
                    data['package']['requirements']['run'][i] = f'{name} =={new_version}'
        t = Template(yaml.dump(data, indent=4)).substitute(SKA_PKG_VERSION='{{ SKA_PKG_VERSION }}',
                                                           SKA_TOP_SRC_DIR='{{ SKA_TOP_SRC_DIR }}')
        with open(meta_file, 'w') as f:
            f.write(t)

"""
Argument order matters. The first "unknown" positional argument is the package.
The rest are included as "unknown" arguments. So the following list of arguments builds ska3-flight:
  ska3-flight --tag master
while this one tries to build master at tag ska3-flight:
  --tag master ska3-flight
To fix this, I can require that packages are specified as a non-positional argument, but that breaks
all current workflows.
"""
def get_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',
                        help="The repository name in format {owner}/{name}")
    parser.add_argument('--skare3-overwrite-version',
                        help="the version of the resulting conda package",
                        default=None)
    parser.add_argument('--skare3-branch',
                        help="The branch to build (default: master",
                        default='master')
    return parser


def main():
    args, unknown_args = get_parser().parse_known_args()

    package = os.path.basename(args.package)

    # these are packages whose name does not match the repository name
    # at this point, automated builds do not know the package name,
    # just the repository name, and the package name determines where to
    # get the configuration.
    package_map = {
        'cmd_states': 'Chandra.cmd_states',
        'eng_archive': 'Ska.engarchive',
    }
    if package in package_map:
        package = package_map[package]

    print(f"Building {package}")

    # setup condarc, because conda does not seem to replace the env variables
    if 'CONDA_PASSWORD' in os.environ:
        condarc = os.path.join(os.path.expandvars('$HOME'), '.condarc')
        condarc_in = condarc + '.in'
        shutil.move(condarc, condarc_in)
        with open(condarc_in) as condarc_in, open(condarc, 'w') as condarc:
            for l in condarc_in.readlines():
                condarc.write(l.replace('${CONDA_PASSWORD}', os.environ['CONDA_PASSWORD']))
    else:
        print('Conda password needs to be given as environmental variable CONDA_PASSWORD')
        sys.exit(100)

    # fetch skare3 (make sure it is there)
    tmp_dir = 'tmp'
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    with tempfile.TemporaryDirectory(dir=tmp_dir) as tmp_dir:
        subprocess.check_call(['git', 'config', '--global', 'user.email', '"aca@cfa.harvard.edu"'])
        subprocess.check_call(['git', 'config', '--global', 'user.name', '"Aspect CI"'])
        skare3_path = os.path.join(tmp_dir, 'skare3')
        print(f'skare3_path: {skare3_path}')
        if os.path.exists(skare3_path):
            subprocess.check_call(['git', 'pull'], cwd=skare3_path)
        else:
            subprocess.check_call(['git', 'clone',
                                   'https://github.com/sot/skare3.git'], cwd=os.path.dirname(skare3_path))
            subprocess.check_call(['git', 'checkout', args.skare3_branch], cwd=skare3_path)

        if args.skare3_overwrite_version:
            rc = re.match('(\S+)rc[0-9]+', args.skare3_overwrite_version)
            if ':' in args.skare3_overwrite_version:
                skare3_old_version, skare3_new_version = args.skare3_overwrite_version.split(':')
            elif rc:
                skare3_new_version = rc.group(0)
                skare3_old_version = rc.group(1)
            else:
                raise Exception(f'wrong format for skare3_overwrite_version: {args.skare3_overwrite_version}')
            skare3_new_version = skare3_new_version.split('/')[-1]
            skare3_old_version = skare3_old_version.split('/')[-1]
            print(f'overwriting skare3 version {skare3_old_version} -> {skare3_new_version}')
            overwrite_skare3_version(skare3_old_version, skare3_new_version, skare3_path)
            # committing because ska_builder.py does not accept dirty repos, but this is not ideal.
            # and setting author so git does not complain
            subprocess.check_call(['git', 'commit', '.', '-m', '"Overwriting version"',
                                   '--author', '"Aspect CI <aca@cfa.harvard.edu>"'],
                                  cwd=skare3_path)

        # do the actual building
        cmd = ['python', 'ska_builder.py', '--github-https', '--force',
               '--build-list', 'ska3_flight_build_order.txt']
        cmd += unknown_args + [package]
        print(' '.join(cmd))
        subprocess.check_call(cmd, cwd=skare3_path)

        print('SKARE3 conda process finished')
        # move resulting files to work dir
        if not os.path.exists('builds'):
            os.makedirs('builds')
        for d in ['linux-64', 'osx-64', 'noarch', 'win-64']:
            print(d)
            d_from = os.path.join(skare3_path, 'builds', d)
            d_to = os.path.join('builds',d)
            if not os.path.exists(d_to):
                os.makedirs(d_to)
            # I do this to make sure the directory is not empty
            with open(os.path.join(d_to, '.ensure-non-empty-dir'), 'w'):
                pass
            if os.path.exists(d_from):
                print(f'SKARE3 moving {d_from} -> {d_to}')
                for filename in glob.glob(os.path.join(d_from, '*')):
                    filename2 = os.path.join(d_to, os.path.basename(filename))
                    if os.path.exists(filename2):
                        os.remove(filename2)
                    shutil.move(filename, filename2)
        print('SKARE3 done')
        rm = glob.glob(os.path.join('builds', '*', '*json*')) + glob.glob(os.path.join('builds', '*', '.*json*'))
        for r in rm:
            os.remove(r)

        # report result
        files = glob.glob(os.path.join('builds', 'linux-64', '*tar.bz2*')) + \
                glob.glob(os.path.join('builds', 'osx-64', '*tar.bz2*')) + \
                glob.glob(os.path.join('builds', 'noarch', '*tar.bz2*')) + \
                glob.glob(os.path.join('builds', 'win-64', '*tar.bz2*'))
        files = ' '.join(files)

        if not files:
            print("No files were built. Something should have been built, right?")
            sys.exit(1)

        print(f'Built files: {files}')
        print(f'::set-output name=files::{files}')


if __name__ == '__main__':
    main()