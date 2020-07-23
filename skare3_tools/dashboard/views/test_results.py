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
    parser = argparse.ArgumentParser()
    parser.add_argument('file_in', default='all_tests.json')
    parser.add_argument('-b', action='store_true', default=False)
    parser.add_argument('--log-dir', default='.')
    parser.add_argument('--static-dir', default=os.path.join(os.path.dirname(dashboard.__file__), 'static'))
    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()
    config = {
        'static_dir': args.static_dir,
        'log_dir': args.log_dir
    }
    if os.path.isdir(args.file_in):
        args.file_in = os.path.join(args.file_in, 'all_tests.json')
    if not os.path.exists(args.file_in):
        print(f'{args.file_in} does not exist')
        parser.print_help()
        parser.exit(1)
    file_out = os.path.join(os.path.dirname(args.file_in), 'test_results.html')
    with open(args.file_in, 'r') as f:
        results = json.load(f)
    with open(file_out, 'w') as out:
        out.write(_render(results, config))
    if not args.b:
        file_out = os.path.abspath(file_out)
        webbrowser.open(f'file://{file_out}', new=2)


if __name__ == '__main__':
    main()
