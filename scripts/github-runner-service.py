#!/usr/bin/env python3.8

import argparse
import logging
import os
import re
import subprocess
import sys

TOP_DIR = "/export/jgonzale/github-workflows"
EXECUTABLE = "./bin/runsvc.sh"


def get_pid(runner):
    pid_file = os.path.join(TOP_DIR, runner, ".service.pid")
    pid = None
    if os.path.exists(pid_file):
        pid = open(pid_file).read().strip()
        logging.debug(f"read pid file. pid={pid}")

    if pid is not None:
        a = subprocess.run(["ps", "-A"], capture_output=True)
        ps = [l for l in a.stdout.decode().split("\n") if re.match(f"{pid}\s", l)]
        if not ps:
            logging.debug(f"process {pid} (runner={runner}) is not running. Resetting.")
            pid = None
    return pid


def status(runner):
    pid = get_pid(runner)
    if pid is not None:
        logging.info(f"Runner {runner} is running with pid={pid}")
    else:
        logging.info(f"Runner {runner} is not running")


def start(runner):
    pid_file = os.path.join(TOP_DIR, runner, ".service.pid")
    log_file = os.path.join(TOP_DIR, runner, ".service.log")
    pid = get_pid(runner)
    if pid is not None:
        logging.debug(f"Process already running with pid={pid} and runner={runner}")
        return

    logging.debug(f"starting {runner} service")
    with open(log_file, "w") as f:
        p = subprocess.Popen(
            [EXECUTABLE],
            cwd=os.path.join(TOP_DIR, runner),
            stdin=f,
            stdout=f,
            stderr=f,
            close_fds=True,
            shell=False,
        )
    pid = f"{p.pid}"
    logging.info(f"service started. pid={pid}. runner={runner}")
    with open(pid_file, "w") as f:
        f.write(pid)


def stop(runner, pid=None):
    if pid is None:
        pid = get_pid(runner)
    if pid is not None:
        logging.info(f"killing process {pid} of {runner}")
        subprocess.run(["kill", pid])


def main():
    logging.basicConfig(level="INFO")
    actions = {"start": start, "stop": stop, "status": status}
    parse = argparse.ArgumentParser()
    parse.add_argument("action", nargs="?", default="start", choices=actions.keys())
    parse.add_argument("--runner", required=True)
    args = parse.parse_args()

    if not os.path.exists(TOP_DIR):
        logging.error(f"Top directory does not exist: {TOP_DIR}")
        sys.exit(1)
    if not os.path.exists(os.path.join(TOP_DIR, args.runner)):
        logging.error(f'No runner "{args.runner}" {TOP_DIR}')
        sys.exit(1)

    actions[args.action](args.runner)


if __name__ == "__main__":
    main()
