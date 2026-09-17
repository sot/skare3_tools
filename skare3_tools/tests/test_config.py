"""
Configuration defaults and upgrade behavior (skare3_tools/config.py).

Behavior pinned:
- The defaults carry ``store_url`` (published data location for HTTP readers)
  and ``config_version`` 3; repository exclusions are NOT config — they live
  in repository_status.json at the store root.
- ``init()`` upgrades an existing older config.json in place: new default
  keys are merged in (user-set values win), obsolete keys are dropped
  (v3 removed ``deprecated_repositories``), and the bumped version is written
  back. Without this, hosts with a pre-existing config.json would silently
  never gain new keys or shed old ones.
- The data directory is never guessed from HOME: it is SKARE3_TOOLS_DATA or
  $SKA/data/skare3/skare3_data, it must exist, and it must be writable when
  init needs to write. Each failure gets its own informative error.
- Exception: a pending version upgrade on a read-only directory (a synced
  host) is kept in memory, not persisted — readers must keep working there.
- Importing never fails for lack of a data directory: commands that only query
  GitHub (release scripts on GitHub-hosted runners) have none. The error is
  raised by ``config.data_dir()``, when the store is actually needed.
- ``init()`` updates CONFIG in place, so modules that imported it by name see
  the change.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import skare3_tools
from skare3_tools import config
from skare3_tools.packages import store

REPO_ROOT = Path(skare3_tools.__file__).parent.parent


def test_default_config_keys():
    assert config._DEFAULT_CONFIG["config_version"] == 4
    assert "deprecated_repositories" not in config._DEFAULT_CONFIG
    assert config._DEFAULT_CONFIG["store_url"].startswith("https://")


def test_init_upgrades_old_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path))
    old = {
        "config_version": 2,
        "repository": "https://github.com/sot/skare3",
        "organizations": ["sot"],  # user-customized value
        "deprecated_repositories": ["sot/skare"],  # obsolete in v3
        "data_dir": str(tmp_path / "data"),
    }
    (tmp_path / "config.json").write_text(json.dumps(old))
    try:
        config.init()
        assert config.CONFIG["config_version"] == 4
        assert config.CONFIG["organizations"] == ["sot"]  # user value kept
        assert "deprecated_repositories" not in config.CONFIG  # obsolete key dropped
        assert "store_url" in config.CONFIG
        on_disk = json.loads((tmp_path / "config.json").read_text())
        assert on_disk["config_version"] == 4  # upgrade persisted
        assert "deprecated_repositories" not in on_disk  # the drop is persisted
        # the derived location is not baked into the file (it travels with the data)
        assert on_disk["data_dir"] == ""
        assert config.CONFIG["data_dir"] == str(tmp_path / "data")
    finally:
        monkeypatch.undo()
        config.init(reset=True)


def test_init_without_ska_fails(monkeypatch):
    monkeypatch.delenv("SKARE3_TOOLS_DATA", raising=False)
    monkeypatch.delenv("SKA", raising=False)
    with pytest.raises(Exception, match="SKA environment variable"):
        config.init()


def test_init_missing_data_dir_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path / "nonexistent"))
    with pytest.raises(Exception, match="does not exist"):
        config.init()


def test_init_unwritable_data_dir_fails(tmp_path, monkeypatch):
    # no config.json in the directory, so init needs to write one
    tmp_path.chmod(0o500)
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path))
    try:
        with pytest.raises(Exception, match="not writable"):
            config.init()
    finally:
        tmp_path.chmod(0o700)


def test_init_upgrade_on_readonly_dir_stays_in_memory(tmp_path, monkeypatch):
    old = {
        "config_version": 2,
        "organizations": ["sot"],
        "deprecated_repositories": ["sot/skare"],
        "data_dir": str(tmp_path / "data"),
    }
    (tmp_path / "config.json").write_text(json.dumps(old))
    tmp_path.chmod(0o500)
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path))
    try:
        config.init()
        assert config.CONFIG["config_version"] == 4  # upgraded in memory
        assert "deprecated_repositories" not in config.CONFIG
        on_disk = json.loads((tmp_path / "config.json").read_text())
        assert on_disk["config_version"] == 2  # nothing persisted
    finally:
        tmp_path.chmod(0o700)
        monkeypatch.undo()
        config.init(reset=True)


def test_init_leaves_current_config_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path))
    current = dict(config._DEFAULT_CONFIG, data_dir=str(tmp_path / "data"))
    (tmp_path / "config.json").write_text(json.dumps(current))
    try:
        config.init()
        assert config.CONFIG == current
    finally:
        monkeypatch.undo()
        config.init(reset=True)


def test_init_ignores_a_data_dir_from_another_machine(tmp_path, monkeypatch):
    """
    config.json is rsynced with the store, so it can name the producer's paths.

    This is exactly what a store copied from the ops machine looks like: the
    file says /proj/sot/ska/... while SKA points somewhere else entirely.
    """
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps(
            dict(
                config._DEFAULT_CONFIG,
                data_dir="/proj/sot/ska/data/skare3/skare3_data/data",
            )
        )
    )
    try:
        config.init()
        assert config.CONFIG["data_dir"] == str(tmp_path / "data")
    finally:
        monkeypatch.undo()
        config.init(reset=True)


def test_init_keeps_a_deliberate_override_inside_the_data_root(tmp_path, monkeypatch):
    """A store elsewhere *under* this data root is this machine's own choice."""
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path))
    elsewhere = tmp_path / "somewhere_else"
    (tmp_path / "config.json").write_text(
        json.dumps(dict(config._DEFAULT_CONFIG, data_dir=str(elsewhere)))
    )
    try:
        config.init()
        assert config.CONFIG["data_dir"] == str(elsewhere)
    finally:
        monkeypatch.undo()
        config.init(reset=True)


def test_import_without_data_dir():
    """A GitHub-only script imports, and the store accessor says what is missing."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("SKA", "SKARE3_TOOLS_DATA")
    }
    code = (
        "import skare3_tools.github.scripts.release_merge_info\n"
        "from skare3_tools import config\n"
        "try:\n"
        "    config.data_dir()\n"
        "except config.DataDirError as error:\n"
        "    print(error)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SKA environment variable" in result.stdout


def test_no_data_dir_means_no_local_store(monkeypatch):
    monkeypatch.setitem(config.CONFIG, "data_dir", "")
    monkeypatch.setattr(config, "_data_dir_error", config.DataDirError("no SKA"))
    with pytest.raises(config.DataDirError, match="no SKA"):
        config.data_dir()
    assert not store.store_present()


def test_init_updates_config_in_place(tmp_path, monkeypatch):
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path))
    before = config.CONFIG
    try:
        config.init(reset=True)
        assert config.CONFIG is before
        assert before["data_dir"] == str(tmp_path / "data")
    finally:
        monkeypatch.undo()
        config.init(reset=True)
