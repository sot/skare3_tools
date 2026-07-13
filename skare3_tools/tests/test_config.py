"""
Configuration defaults and upgrade behavior (skare3_tools/config.py).

Behavior pinned:
- The defaults carry the P2 keys: ``deprecated_repositories`` (repos excluded
  from the data store), ``store_url`` (published data location for HTTP
  readers), and ``config_version`` 2.
- ``init()`` upgrades an existing older config.json in place: new default
  keys are merged in (user-set values win) and the bumped version is written
  back. Without this, hosts with a pre-existing config.json would silently
  never gain new keys.
"""

import json

from skare3_tools import config


def test_default_config_has_p2_keys():
    assert config._DEFAULT_CONFIG["config_version"] == 2
    deprecated = config._DEFAULT_CONFIG["deprecated_repositories"]
    assert "acisops/dpa_check" in deprecated
    assert "sot/skare" in deprecated  # the dashboard always excluded it
    assert len(deprecated) == 7
    assert config._DEFAULT_CONFIG["store_url"].startswith("https://")


def test_init_upgrades_old_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SKARE3_TOOLS_DATA", str(tmp_path))
    old = {
        "config_version": 1,
        "repository": "https://github.com/sot/skare3",
        "organizations": ["sot"],  # user-customized value
        "data_dir": str(tmp_path / "data"),
    }
    (tmp_path / "config.json").write_text(json.dumps(old))
    try:
        config.init()
        assert config.CONFIG["config_version"] == 2
        assert config.CONFIG["organizations"] == ["sot"]  # user value kept
        assert "deprecated_repositories" in config.CONFIG
        assert "store_url" in config.CONFIG
        on_disk = json.loads((tmp_path / "config.json").read_text())
        assert on_disk["config_version"] == 2  # upgrade persisted
    finally:
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
