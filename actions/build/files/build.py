#!/usr/bin/env python3

import sys
import os
import subprocess
import glob
import shutil


package = os.path.basename(sys.argv[1])
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
skare3_path = 'tmp/skare3'
if not os.path.exists(os.path.dirname(skare3_path)):
    os.makedirs(os.path.dirname(skare3_path))
if os.path.exists(skare3_path):
    subprocess.check_call(['git', 'pull'], cwd=skare3_path)
else:
    subprocess.check_call(['git', 'clone', '--single-branch', '--branch', 'master',
                           'https://github.com/sot/skare3.git'], cwd=os.path.dirname(skare3_path))

# do the actual building
cmd = ['./ska_builder.py', '--force',
       '--build-list', './ska3_flight_build_order.txt']
cmd += sys.argv[2:] + [package]
print(' '.join(cmd))
subprocess.check_call(cmd, cwd=skare3_path)

# move resulting files to work dir
os.makedirs('builds')
for d in ['linux-64', 'osx-64', 'noarch']:
    d = os.path.join(skare3_path, 'builds', d)
    if os.path.exists(d):
        shutil.move(d, 'builds')

rm = glob.glob('builds/*/*json*') + glob.glob('builds/*/.*json*')
for r in rm:
    os.remove(r)

# report result
files = glob.glob('builds/linux-64/*tar.bz2*') + \
        glob.glob('builds/osx-64/*tar.bz2*') + \
        glob.glob('builds/noarch/*tar.bz2*')
files = ' '.join(files)

print(f'Built files: {files}')
print(f'::set-output name=files::{files}')
