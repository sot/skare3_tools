#!/usr/bin/env python3

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
        for i in range(len(data['requirements'])):
            if re.search('==', data['requirements']['run'][i]):
                name, pkg_version = data['requirements']['run'][i].split('==')
                name = name.strip()
                if name in meta_pkgs and pkg_version == current_version:
                    data['requirements']['run'][i] = f'{name} =={new_version}'
        t = Template(yaml.dump(data, indent=4)).substitute(SKA_PKG_VERSION='{{ SKA_PKG_VERSION }}',
                                                           SKA_TOP_SRC_DIR='{{ SKA_TOP_SRC_DIR }}')
        with open(meta_file, 'w') as f:
            f.write(t)


parser = argparse.ArgumentParser()
parser.add_argument('package')
parser.add_argument('--skare3-overwrite-version', default=None)
parser.add_argument('--skare3-branch', default='master')

args, unknown_args = parser.parse_known_args()

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
            condarc.write(l.replace('${CONDA_PASSWORD}', os.environ['CONDA_PASSWORD']))
else:
    print('Conda password needs to be given as environmental variable CONDA_PASSWORD')
    sys.exit(100)

# fetch skare3 (make sure it is there)
skare3_path = '/home/ska/tmp/skare3'
if not os.path.exists(os.path.dirname(skare3_path)):
    os.makedirs(os.path.dirname(skare3_path))
if os.path.exists(skare3_path):
    subprocess.check_call(['git', 'pull'], cwd=skare3_path)
else:
    subprocess.check_call(['git', 'clone', '--single-branch', '--branch', args.skare3_branch,
                           'https://github.com/sot/skare3.git'], cwd=os.path.dirname(skare3_path))


if args.skare3_overwrite_version:
    skare3_old_version, skare3_new_version = args.skare3_overwrite_version.split(':')
    print(f'overwriting skare3 version {skare3_old_version} -> {skare3_new_version}')
    overwrite_skare3_version(skare3_old_version, skare3_new_version, skare3_path)
    # committing because ska_builder.py does not accept dirty repos, but this is not ideal.
    subprocess.check_call(['git', 'commit', '.', '-m', '"Overwriting version"'],
                          cwd=skare3_path)

# do the actual building
cmd = ['./ska_builder.py', '--github-https',
       '--build-list', './ska3_flight_build_order.txt']
cmd += unknown_args + [package]
print(' '.join(cmd))
subprocess.check_call(cmd, cwd=skare3_path)

# move resulting files to work dir
if not os.path.exists('builds'):
    os.makedirs('builds')
for d in ['linux-64', 'osx-64', 'noarch']:
    d_from = os.path.join(skare3_path, 'builds', d)
    if os.path.exists(d_from):
        d_to = os.path.join('builds',d)
        if not os.path.exists(d_to):
            os.makedirs(d_to)
        for filename in glob.glob(os.path.join(d_from, '*')):
            filename2 = os.path.join(d_to, os.path.basename(filename))
            if os.path.exists(filename2):
                os.remove(filename2)
            shutil.move(filename, filename2)

rm = glob.glob('builds/*/*json*') + glob.glob('builds/*/.*json*')
for r in rm:
    os.remove(r)

# report result
files = glob.glob('builds/linux-64/*tar.bz2*') + \
        glob.glob('builds/osx-64/*tar.bz2*') + \
        glob.glob('builds/noarch/*tar.bz2*')
files = ' '.join(files)

if not files:
    print("No files were built. Something should have been built, right?")
    sys.exit(1)

print(f'Built files: {files}')
print(f'::set-output name=files::{files}')
