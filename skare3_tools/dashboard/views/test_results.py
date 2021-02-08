#!/usr/bin/env python3

import argparse
import json
import os
from skare3_tools import dashboard, test_results as tr
import webbrowser


def test_results():
    test_run = tr.get()[-1]
    config = {
        'static_dir': 'static',
        'log_dir': "tests/logs/{uid}".format(uid=test_run['run_info']['uid'])
    }
    return _render(test_run, config)


def _render(tests, config):
    if 'run_info' not in tests:
        tests['run_info'] = {k: '' for k in ['date', 'ska_version', 'system', 'architecture',
                                             'hostname', 'platform']}
    for ts in tests['test_suites']:
        n_skipped = 0
        n_fail = 0
        n_pass = 0
        for tc in ts['test_cases']:
            if ('log' not in tc or not tc['log']) and 'log' in ts:
                tc['log'] = ts['log']
            if tc['status'] == 'pass':
                n_pass += 1
            elif tc['status'] == 'fail':
                n_fail += 1
            elif tc['status'] == 'skipped':
                n_skipped += 1
            if 'err_message' in tc:
                tc['message'] = tc['err_message']
        if n_fail > 0:
            ts['status'] = 'fail'
        elif n_pass == 0 and n_skipped > 0:
            ts['status'] = 'skipped'
        else:
            ts['status'] = 'pass'
        ts['skip'] = n_skipped
        ts['pass'] = n_pass
        ts['fail'] = n_fail

    template = dashboard.get_template('test-results.html')
    return template.render(title='Skare3 Tests', data=tests, config=config)


def get_parser():
    parser = argparse.ArgumentParser(
        description="Produce a single html page with a test result report"
    )
    parser.add_argument('-i',
                        help="Directory or JSON file containing all test results. "
                             "If it is a directory, then it must have a file named all_tests.json.",
                        dest='file_in')
    parser.add_argument('-o',
                        help="Name of file to write to. By default, this creates a file named "
                             "index.html, located in the input directory or the current "
                             "working directory, depending on whether the '-i' options was given.",
                        dest='file_out')
    parser.add_argument('-b', action='store_true', default=False,
                        help='Batch mode: do not open a browser window with the result.')
    parser.add_argument('--log-dir', default='.')
    parser.add_argument('--static-dir',
                        help="Location of static data directory.",
                        default='https://cxc.cfa.harvard.edu/mta/ASPECT/skare3/dashboard/static')
    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()
    config = {
        'static_dir': args.static_dir,
        'log_dir': args.log_dir
    }
    if args.file_in and os.path.isdir(args.file_in):
        args.file_in = os.path.join(args.file_in, 'all_tests.json')

    if args.file_out is None:
        if args.file_in:
            args.file_out = os.path.join(os.path.dirname(args.file_in), 'index.html')
        else:
            args.file_out = 'index.html'

    if args.file_in and not os.path.exists(args.file_in):
        print('{filename} does not exist'.format(filename=args.file_in))
        parser.print_help()
        parser.exit(1)

    if not args.file_in:
        results = tr.get()[-1]
    else:
        with open(args.file_in, 'r') as f:
            results = json.load(f)

    with open(args.file_out, 'w') as out:
        out.write(_render(results, config))

    if not args.b:
        file_out = os.path.abspath(args.file_out)
        webbrowser.open('file://{file_out}'.format(file_out=args.file_out), new=2)


if __name__ == '__main__':
    main()
