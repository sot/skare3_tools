"""
The dashboard-update publisher (skare3_tools/scripts/dashboard_update.py).

Behavior pinned:
- publish() copies every file in PUBLISHED_FILES (packages.json,
  package_list.json, test_results.json, repository_status.json).
- manifest.json is never published (it would clobber the React app's own
  manifest.json at the public root).
- Copies are atomic: no .tmp leftovers.
- A missing store file fails loudly.
"""

import json

import pytest

from skare3_tools.scripts import dashboard_update


@pytest.fixture()
def dirs(tmp_path):
    data = tmp_path / "data"
    pub = tmp_path / "public"
    data.mkdir()
    pub.mkdir()
    for name in dashboard_update.PUBLISHED_FILES:
        (data / name).write_text(json.dumps({"file": name}))
    (data / "manifest.json").write_text("{}")
    return data, pub


def test_publish_copies_store_files(dirs):
    data, pub = dirs
    dashboard_update.publish(pub, data_dir=data)
    for name in dashboard_update.PUBLISHED_FILES:
        assert json.loads((pub / name).read_text()) == {"file": name}
    assert not (pub / "manifest.json").exists()
    assert not list(pub.rglob("*.tmp"))


def test_published_files_include_the_package_list(dirs):
    """The HTTP tier reads it, so it has to be published with the aggregate."""
    assert "package_list.json" in dashboard_update.PUBLISHED_FILES


def test_publish_missing_file_fails(dirs):
    data, pub = dirs
    (data / "packages.json").unlink()
    with pytest.raises(FileNotFoundError):
        dashboard_update.publish(pub, data_dir=data)
