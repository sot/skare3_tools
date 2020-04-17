#!/usr/bin/env python3

import json
from jinja2 import Environment, PackageLoader, select_autoescape
import argparse
import datetime


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', default='test_results.json')
    parser.add_argument('-o', default='test_results.html')
    return parser


def main():

    args = get_parser().parse_args()

    with open(args.i, 'r') as f:
        results = json.load(f)

    env = Environment(
        loader=PackageLoader('skare3_tools.dashboard', 'templates'),
        autoescape=select_autoescape(['html', 'xml'])
    )

    template = env.get_template('test-results.tpl')

    with open(args.o, 'w') as out:
        out.write(template.render(title='Skare3 Tests',
                                  results=results))


if __name__ == '__main__':
    main()
