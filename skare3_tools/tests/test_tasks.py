"""
The skare3-tasks crontab harness (skare3_tools/scripts/tasks.py).

Behavior pinned:
- ci_auth_env returns the environment exported by sourcing the file in bash.
- Every entry in TASKS resolves to a config file shipped with the package.
- run_task launches task_schedule3.pl with the packaged config, with the
  secrets loaded and this environment's bin dir first on PATH.
"""

import subprocess
import sys
from importlib import resources
from pathlib import Path

from skare3_tools.scripts import tasks


def test_ci_auth_env(tmp_path):
    auth = tmp_path / "ci-auth"
    auth.write_text(
        "export CONDA_PASSWORD=hunter2\nexport SKARE3_GITHUB_APP_KEY=$HOME/key.pem\n"
    )
    env = tasks.ci_auth_env(auth)
    assert env["CONDA_PASSWORD"] == "hunter2"
    assert env["SKARE3_GITHUB_APP_KEY"] == str(Path.home() / "key.pem")


def test_task_configs_are_packaged():
    for cfg in tasks.TASKS.values():
        assert (resources.files("skare3_tools") / "task_schedules" / cfg).is_file()


def test_run_task(monkeypatch):
    monkeypatch.setattr(tasks, "ci_auth_env", lambda: {"CONDA_PASSWORD": "hunter2"})
    calls = {}

    def fake_run(cmd, env=None, **kwargs):
        calls["cmd"] = cmd
        calls["env"] = env
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(tasks.subprocess, "run", fake_run)
    assert tasks.run_task("dashboard") == 0
    assert calls["cmd"][:2] == ["task_schedule3.pl", "-config"]
    assert calls["cmd"][2].endswith("dashboard.cfg")
    assert calls["env"]["CONDA_PASSWORD"] == "hunter2"
    assert calls["env"]["PATH"].startswith(str(Path(sys.executable).parent))
