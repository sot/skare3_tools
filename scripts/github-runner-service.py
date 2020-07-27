#!/usr/bin/env python3.8

import subprocess
import re
import os
import logging
import argparse


TOP_DIR = '/export/jgonzale/github-workflows/skare3-runner'
PID_FILE = os.path.join(TOP_DIR, '.service.pid')
LOG_FILE = os.path.join(TOP_DIR, '.service.log')
EXECUTABLE = "./bin/runsvc.sh"


def get_pid():
    pid = None
    if os.path.exists(PID_FILE):
        pid = open(PID_FILE).read().strip()
        logging.debug(f'read pid file. pid={pid}')

    if pid is not None:
        a = subprocess.run(['ps', '-A'], capture_output=True)
        ps = [l for l in a.stdout.decode().split('\n') if re.match(f'{pid}\s', l)]
        if not ps:
            logging.debug(f'process {pid} is not running. Resetting.')
            pid = None
    return pid


def start():
    pid = get_pid()
    if pid is not None:
        logging.debug(f'Process already running with pid={pid}')
        return

    logging.debug('starting service')
    with open(LOG_FILE, 'w') as f:
        p = subprocess.Popen([EXECUTABLE],
                             cwd=TOP_DIR,
                             stdin=f, stdout=f, stderr=f, close_fds=True, shell=False)
    pid = f'{p.pid}'
    logging.info(f'service started. pid={pid}')
    with open(PID_FILE, 'w') as f:
        f.write(pid)


def stop(pid=None):
    if pid is None:
        pid = get_pid()
    if pid is not None:
        logging.info(f'killing process {pid}')
        subprocess.run(['kill', pid])


def main():
    logging.basicConfig(level='INFO')
    actions = {
        'start': start,
        'stop': stop
    }
    parse = argparse.ArgumentParser()
    parse.add_argument('action', nargs='?', default='start', choices=actions.keys())
    args = parse.parse_args()

    if not os.path.exists(TOP_DIR):
        logging.error(f'Top directory does not exist: {TOP_DIR}')

    actions[args.action]()


if __name__ == '__main__':
    main()
