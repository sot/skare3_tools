#!/usr/bin/env python3

import json
from jinja2 import Environment, PackageLoader, select_autoescape
import argparse
import datetime


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', default='repository_info.json')
    parser.add_argument('-o', default='index.html')
    return parser


def main():

    args = get_parser().parse_args()

    with open(args.i, 'r') as f:
        info = json.load(f)

    info['packages'] = sorted(info['packages'], key=lambda p: p['name'])
    for p in info['packages']:
        for pr in p['pull_requests']:
            pr['last_commit_date'] = \
                datetime.datetime.strptime(pr['last_commit_date'],
                                           "%Y-%m-%dT%H:%M:%SZ").date().isoformat()

    env = Environment(
        loader=PackageLoader('skare3_tools.dashboard', 'templates'),
        autoescape=select_autoescape(['html', 'xml'])
    )

    template = env.get_template('dashboard-watable.tpl')

    with open(args.o, 'w') as out:
        out.write(template.render(title='Skare3 Packages',
                                  info=info))


if __name__ == '__main__':
    main()
