#!/usr/bin/env python3
"""
Gather test results from log file.
"""

import re
import os
import json
import argparse
import importlib


def parser():
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument('directory')
    parse.add_argument('-o', default='test_results.json')
    return parse


def main():
    args = parser().parse_args()
    directory = args.directory

    filename = os.path.join(directory, 'test.log')
    with open(filename) as f:
        for l in f:
            if re.match('\*\*\*\s+Package\s+Script\s+Status\s+\*\*\*', l):
                break
        results = []
        for l in f:
            if re.search('fail', l.lower()) or re.search('pass',l.lower()):
                results.append(l.split()[1:-1])
        result_dict = {k[0]: {'tests': {}} for k in results}
        for k in results:
            try:
                module = importlib.import_module(k[0])
                version = module.__version__
            except:
                version = ''
            result_dict[k[0]]['tests'][k[1]] = k[2].upper()
            res = result_dict[k[0]]['tests'].values()
            result_dict[k[0]]['pass'] = not sum([r=='FAIL' for r in res])
            result_dict[k[0]]['version'] = version

            test_results = {'log_directory': directory,
                            'results':result_dict}
            with open(args.o, 'w') as f:
                json.dump(test_results, f, indent=2)


if __name__ == '__main__':
    main()
