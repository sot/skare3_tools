"""
The skare3-tasks crontab harness (skare3_tools/scripts/tasks.py).

Behavior pinned:
- ci_auth_env returns the environment exported by sourcing the file in bash.
- Every entry in TASKS resolves to a config file shipped with the package.
- run_task launches task_schedule3.pl with the packaged config, with the
  secrets loaded and this environment's bin dir first on PATH.
- A missing or unreadable secrets file is reported as what it is: cron mails
  the message, so it says which file is missing and what it is needed for,
  with no traceback.
"""

import subprocess
import sys
from importlib import resources
from pathlib import Path

import pytest

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


def test_ci_auth_env_without_the_file(tmp_path):
    with pytest.raises(tasks.TaskError, match="secrets file"):
        tasks.ci_auth_env(tmp_path / "ci-auth")


def test_ci_auth_env_with_an_unreadable_file(tmp_path):
    auth = tmp_path / "ci-auth"
    auth.write_text("export CONDA_PASSWORD=(\n")  # a syntax error bash reports
    with pytest.raises(tasks.TaskError, match=str(auth)):
        tasks.ci_auth_env(auth)


def test_main_reports_the_error_without_a_traceback(monkeypatch, capsys):
    def missing():
        raise tasks.TaskError("missing secrets file /home/kadi/.ci-auth")

    monkeypatch.setattr(tasks, "ci_auth_env", missing)
    monkeypatch.setattr(sys, "argv", ["skare3-tasks", "dashboard"])
    with pytest.raises(SystemExit) as exit_info:
        tasks.main()
    assert exit_info.value.code != 0
    assert "missing secrets file" in str(exit_info.value.code)
