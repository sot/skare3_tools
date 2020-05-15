#!/usr/bin/env python3

import os
import json
from jinja2 import Environment, PackageLoader, select_autoescape
import argparse
import datetime


package_name_map = [
  {
    "name": "Chandra.Maneuver",
    "package": "chandra.maneuver",
    "repo": "sot/Chandra.Maneuver"
  },
  {
    "name": "Chandra.Time",
    "package": "chandra.time",
    "repo": "sot/Chandra.Time"
  },
  {
    "name": "Chandra.cmd_states",
    "package": "chandra.cmd_states",
    "repo": "sot/cmd_states"
  },
  {
    "name": "Quaternion",
    "package": "quaternion",
    "repo": "sot/Quaternion"
  },
  {
    "name": "Ska.DBI",
    "package": "ska.dbi",
    "repo": "sot/Ska.DBI"
  },
  {
    "name": "Ska.File",
    "package": "ska.file",
    "repo": "sot/Ska.File"
  },
  {
    "name": "Ska.Matplotlib",
    "package": "ska.matplotlib",
    "repo": "sot/Ska.Matplotlib"
  },
  {
    "name": "Ska.Numpy",
    "package": "ska.numpy",
    "repo": "sot/Ska.Numpy"
  },
  {
    "name": "Ska.ParseCM",
    "package": "ska.parsecm",
    "repo": "sot/Ska.ParseCM"
  },
  {
    "name": "Ska.Shell",
    "package": "ska.shell",
    "repo": "sot/Ska.Shell"
  },
  {
    "name": "Ska.Sun",
    "package": "ska.sun",
    "repo": "sot/Ska.Sun"
  },
  {
    "name": "Ska.arc5gl",
    "package": "ska.arc5gl",
    "repo": "sot/Ska.arc5gl"
  },
  {
    "name": "Ska.astro",
    "package": "ska.astro",
    "repo": "sot/Ska.astro"
  },
  {
    "name": "Ska.engarchive",
    "package": "ska.engarchive",
    "repo": "sot/eng_archive"
  },
  {
    "name": "Ska.ftp",
    "package": "ska.ftp",
    "repo": "sot/Ska.ftp"
  },
  {
    "name": "Ska.quatutil",
    "package": "ska.quatutil",
    "repo": "sot/Ska.quatutil"
  },
  {
    "name": "Ska.tdb",
    "package": "ska.tdb",
    "repo": "sot/Ska.tdb"
  },
  {
    "name": "aca_egse",
    "package": "aca_egse",
    "repo": "sot/aca_egse"
  },
  {
    "name": "acdc",
    "package": "acdc",
    "repo": "sot/acdc"
  },
  {
    "name": "acis_taco",
    "package": "acis_taco",
    "repo": "sot/taco"
  },
  {
    "name": "acis_thermal_check",
    "package": "acis_thermal_check",
    "repo": "acisops/acis_thermal_check"
  },
  {
    "name": "acisfp_check",
    "package": "acisfp_check",
    "repo": "acisops/acisfp_check"
  },
  {
    "name": "agasc",
    "package": "agasc",
    "repo": "sot/agasc"
  },
  {
    "name": "annie",
    "package": "annie",
    "repo": "sot/annie"
  },
  {
    "name": "backstop_history",
    "package": "backstop_history",
    "repo": "acisops/backstop_history"
  },
  {
    "name": "chandra_aca",
    "package": "chandra_aca",
    "repo": "sot/chandra_aca"
  },
  {
    "name": "cxotime",
    "package": "cxotime",
    "repo": "sot/cxotime"
  },
  {
    "name": "dea_check",
    "package": "dea_check",
    "repo": "acisops/dea_check"
  },
  {
    "name": "dpa_check",
    "package": "dpa_check",
    "repo": "acisops/dpa_check"
  },
  {
    "name": "find_attitude",
    "package": "find_attitude",
    "repo": "sot/find_attitude"
  },
  {
    "name": "hopper",
    "package": "hopper",
    "repo": "sot/hopper"
  },
  {
    "name": "kadi",
    "package": "kadi",
    "repo": "sot/kadi"
  },
  {
    "name": "maude",
    "package": "maude",
    "repo": "sot/maude"
  },
  {
    "name": "mica",
    "package": "mica",
    "repo": "sot/mica"
  },
  {
    "name": "parse_cm",
    "package": "parse_cm",
    "repo": "sot/parse_cm"
  },
  {
    "name": "proseco",
    "package": "proseco",
    "repo": "sot/proseco"
  },
  {
    "name": "psmc_check",
    "package": "psmc_check",
    "repo": "acisops/psmc_check"
  },
  {
    "name": "pyyaks",
    "package": "pyyaks",
    "repo": "sot/pyyaks"
  },
  {
    "name": "ska_helpers",
    "package": "ska_helpers",
    "repo": "sot/ska_helpers"
  },
  {
    "name": "ska_path",
    "package": "ska_path",
    "repo": "sot/ska_path"
  },
  {
    "name": "ska_sync",
    "package": "ska_sync",
    "repo": "sot/ska_sync"
  },
  {
    "name": "sparkles",
    "package": "sparkles",
    "repo": "sot/sparkles"
  },
  {
    "name": "starcheck",
    "package": "starcheck",
    "repo": "sot/starcheck"
  },
  {
    "name": "tables3_api",
    "package": "tables3_api",
    "repo": "sot/tables3_api"
  },
  {
    "name": "task_schedule",
    "package": "task_schedule",
    "repo": "sot/task_schedule"
  },
  {
    "name": "testr",
    "package": "testr",
    "repo": "sot/testr"
  },
  {
    "name": "watch_cron_logs",
    "package": "watch_cron_logs",
    "repo": "sot/watch_cron_logs"
  },
  {
    "name": "xija",
    "package": "xija",
    "repo": "sot/xija"
  }
]

def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', default='repository_info.json')
    parser.add_argument('-o', default='index.html')
    parser.add_argument('-t', default='test_results.json')
    return parser


def main():

    args = get_parser().parse_args()

    exclude = ['skare']

    with open(args.i, 'r') as f:
        info = json.load(f)

    if os.path.exists(args.t):
        with open(args.t, 'r') as f:
            test_results = json.load(f)
    else:
        test_results = {}

    repo2name = {p['repo']: p['name'] for p in package_name_map}

    info['packages'] = sorted([p for p in info['packages'] if p['name'] not in exclude], key=lambda p: p['name'])
    for p in info['packages']:
        for pr in p['pull_requests']:
            pr['last_commit_date'] = \
                datetime.datetime.strptime(pr['last_commit_date'],
                                           "%Y-%m-%dT%H:%M:%SZ").date().isoformat()
        repo = f"{p['owner']}/{p['name']}"
        if repo in repo2name and repo2name[repo] in test_results['results']:
            r = test_results['results'][repo2name[repo]]
            p['test_version'] = r['version']
            p['test_status'] = 'PASS' if r['pass'] else 'FAIL'
        else:
            p['test_version'] = ''
            p['test_status'] = ''

    env = Environment(
        loader=PackageLoader('skare3_tools.dashboard', 'templates'),
        autoescape=select_autoescape(['html', 'xml'])
    )

    template = env.get_template('dashboard-watable.html')

    with open(args.o, 'w') as out:
        out.write(template.render(title='Skare3 Packages',
                                  info=info))


if __name__ == '__main__':
    main()
