"""
Launch skare3 scheduled tasks — the crontab entry point.

Each task is a task_schedule3.pl run with a configuration shipped in this
package (``skare3_tools/task_schedules/``), so the crontab line is the whole
host-side installation::

    0 * * * * /path/to/env/bin/skare skare3-tasks dashboard

The harness supplies what cron does not: the secrets exported by
``~/.ci-auth``, and the PATH of the environment this script is installed in,
so the config's exec lines resolve to the same environment.
"""

import argparse
import json
import os
import subprocess
import sys
from importlib import resources
from pathlib import Path

TASKS = {"dashboard": "dashboard.cfg"}


def ci_auth_env(path="~/.ci-auth"):
    """The environment after sourcing ``path`` in bash (a la ska_shell.getenv)."""
    dump = f'{sys.executable} -c "import os, json; print(json.dumps(dict(os.environ)))"'
    out = subprocess.run(
        ["bash", "-c", f"source {Path(path).expanduser()} && exec {dump}"],
        capture_output=True,
        check=True,
    ).stdout
    return json.loads(out)


def run_task(name):
    env = os.environ | ci_auth_env()
    env["PATH"] = f"{Path(sys.executable).parent}:{env['PATH']}"
    cfg = resources.files("skare3_tools") / "task_schedules" / TASKS[name]
    with resources.as_file(cfg) as path:
        result = subprocess.run(
            ["task_schedule3.pl", "-config", str(path)], env=env, check=False
        )
    return result.returncode


def get_parser():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("task", choices=TASKS)
    return parser


def main():
    args = get_parser().parse_args()
    sys.exit(run_task(args.task))


if __name__ == "__main__":
    main()
