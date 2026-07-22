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
"""

import json

import pytest

from skare3_tools import config


def test_default_config_keys():
    assert config._DEFAULT_CONFIG["config_version"] == 3
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
        assert config.CONFIG["config_version"] == 3
        assert config.CONFIG["organizations"] == ["sot"]  # user value kept
        assert "deprecated_repositories" not in config.CONFIG  # obsolete key dropped
        assert "store_url" in config.CONFIG
        on_disk = json.loads((tmp_path / "config.json").read_text())
        assert on_disk["config_version"] == 3  # upgrade persisted
        assert "deprecated_repositories" not in on_disk  # the drop is persisted
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
