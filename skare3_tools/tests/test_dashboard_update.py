"""
The dashboard-update publisher (skare3_tools/packages/dashboard_update.py).

Behavior pinned:
- publish() copies packages.json, test_results.json and repository_status.json
  and mirrors the repos/ tree (new files appear, stale files disappear).
- manifest.json is never published (it would clobber the React app's own
  manifest.json at the public root).
- Copies are atomic: no .tmp leftovers.
- A missing store file fails loudly.
"""

import json

import pytest

# the refresh import chain needs cxotime, which is not pip-installable
# (unavailable in the PR workflow environment)
pytest.importorskip("cxotime")

from skare3_tools.packages import dashboard_update  # noqa: E402


@pytest.fixture()
def dirs(tmp_path):
    data = tmp_path / "data"
    pub = tmp_path / "public"
    (data / "repos" / "sot").mkdir(parents=True)
    pub.mkdir()
    for name in dashboard_update.PUBLISHED_FILES:
        (data / name).write_text(json.dumps({"file": name}))
    (data / "manifest.json").write_text("{}")
    (data / "repos" / "sot" / "foo.json").write_text('{"name": "foo"}')
    return data, pub


def test_publish_copies_store_files(dirs):
    data, pub = dirs
    dashboard_update.publish(pub, data_dir=data)
    for name in dashboard_update.PUBLISHED_FILES:
        assert json.loads((pub / name).read_text()) == {"file": name}
    assert json.loads((pub / "repos" / "sot" / "foo.json").read_text()) == {
        "name": "foo"
    }
    assert not (pub / "manifest.json").exists()
    assert not list(pub.rglob("*.tmp"))


def test_publish_mirrors_repos(dirs):
    data, pub = dirs
    dashboard_update.publish(pub, data_dir=data)
    (data / "repos" / "sot" / "foo.json").unlink()
    (data / "repos" / "acisops").mkdir()
    (data / "repos" / "acisops" / "bar.json").write_text('{"name": "bar"}')
    dashboard_update.publish(pub, data_dir=data)
    assert not (pub / "repos" / "sot" / "foo.json").exists()
    assert (pub / "repos" / "acisops" / "bar.json").exists()


def test_publish_missing_file_fails(dirs):
    data, pub = dirs
    (data / "packages.json").unlink()
    with pytest.raises(FileNotFoundError):
        dashboard_update.publish(pub, data_dir=data)
