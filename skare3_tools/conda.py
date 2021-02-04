import os
import subprocess
import json
from pathlib import Path
import shutil


def gather_env_pkgs(directory, pkgs_dir=None, include_channels=None, exclude_channels=()):
    directory = Path(directory)
    if pkgs_dir is None:
        parts = []
        for part in Path(os.environ['CONDA_PREFIX']).parts:
            if part == 'envs':
                parts.append('pkgs')
                break
            else:
                parts.append(part)
        pkgs_dir = Path(*parts)
    pkgs = json.loads(subprocess.check_output(['conda', 'list', '--json']).decode())
    pkgs = [p for p in pkgs if p['channel'] not in exclude_channels]
    if include_channels:
        pkgs = [p for p in pkgs if p['channel'] in include_channels]
    if pkgs and not directory.exists():
        directory.mkdir()
    for pkg in pkgs:
        name = ''
        if (pkgs_dir / f'{pkg["dist_name"]}.conda').exists():
            name = pkgs_dir / f'{pkg["dist_name"]}.conda'
        elif (pkgs_dir / f'{pkg["dist_name"]}.tar.bz2').exists():
            name = pkgs_dir / f'{pkg["dist_name"]}.tar.bz2'
        shutil.copy(name, directory)
