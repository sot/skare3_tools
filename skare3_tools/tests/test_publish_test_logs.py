"""
The testr log publisher (skare3_tools/scripts/publish_test_logs.py).

Behavior pinned:
- publish_logs() copies the source into a timestamped directory under the
  archive and points the ``last`` symlink at it, replacing a previous one.
- A symlinked source (logs/last) is resolved before copying.
"""

from skare3_tools.scripts import publish_test_logs


def test_publish_logs(tmp_path):
    source = tmp_path / "run"
    source.mkdir()
    (source / "all_tests.json").write_text("{}")
    last_link = tmp_path / "last"
    last_link.symlink_to(source)  # publish through a symlink, like logs/last

    archive = tmp_path / "archive"
    archive.mkdir()
    previous = archive / "2026-01-01T00:00:00"
    previous.mkdir()
    (archive / "last").symlink_to(previous)  # stale link from an earlier run

    dest = publish_test_logs.publish_logs(last_link, archive)
    assert dest.parent == archive
    assert (dest / "all_tests.json").read_text() == "{}"
    assert (archive / "last").resolve() == dest.resolve()  # link replaced
