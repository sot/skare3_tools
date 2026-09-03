"""
The test-results store (skare3_tools/test_results.py).

Behavior pinned:
- add()/get()/get_latest()/streams() round-trip through the store at
  CONFIG["data_dir"]/test_logs, resolved lazily at call time (no
  import-time directory creation), so the producer can point it anywhere.
- A duplicate add is refused; reading a store that was never written raises
  FileNotFoundError (callers treat that as "no results yet").
- The index outlives the runs it references (remove_older_than prunes them, a
  partial copy has fewer runs than entries), so a pruned run is skipped rather
  than fatal, and get_latest reads only the newest readable run.
- remove_older_than reads the date testr actually writes (%Y:%m:%dT%H:%M:%S,
  the format used by the runs in the store), and prunes by index entry, so an
  entry whose run is already gone still ages out.
"""

import json
import shutil
from datetime import datetime, timedelta

import pytest

from skare3_tools import test_results as tr
from skare3_tools.config import CONFIG

ALL_TESTS = {
    "run_info": {
        "date": "2026:07:12T00:00:00",
        "ska_version": "2026.5",
        "system": ["Linux"],
        "architecture": ["x86_64"],
        "hostname": ["kady"],
        "platform": ["linux-x86_64"],
    },
    "test_suites": [
        {
            "package": "foo",
            "properties": {
                "package_version": "1.0.0",
                "architecture": "x86_64",
                "hostname": "kady",
                "system": "Linux",
                "platform": "linux-x86_64",
            },
            "test_cases": [
                {"name": "test_one", "status": "pass"},
                {
                    "name": "test_two",
                    "status": "skipped",
                    "skipped": {"message": "not today", "output": ""},
                },
            ],
        }
    ],
}


def test_add_get_roundtrip(tmp_path, monkeypatch):
    # a data dir where nothing exists yet: add() must create the store
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "all_tests.json").write_text(json.dumps(ALL_TESTS))

    tr.add(run_dir, stream="ska3-masters")

    results = tr.get(stream="ska3-masters")
    assert len(results) == 1
    latest = tr.get_latest(stream="ska3-masters")
    suite = latest["test_suites"][0]
    assert suite["status"] == "pass"
    assert suite["n_pass"] == 1
    assert suite["n_skip"] == 1
    assert latest["run_info"]["stream"] == "ska3-masters"
    assert tr.streams() == {"ska3-masters"}
    # the per-stream symlink points at the ingested run
    assert (tmp_path / "test_logs" / "ska3-masters" / "all_tests.json").exists()

    with pytest.raises(tr.TestResultException, match="already exist"):
        tr.add(run_dir, stream="ska3-masters")


def test_get_on_missing_store_raises(tmp_path, monkeypatch):
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path / "nothing"))
    with pytest.raises(FileNotFoundError):
        tr.get()


def _ingest(tmp_path, stream, date, package_version):
    """Ingest one run, dated, and return its store directory."""
    run_dir = tmp_path / f"run_{date}"
    run_dir.mkdir()
    run = json.loads(json.dumps(ALL_TESTS))
    run["run_info"]["date"] = date
    run["test_suites"][0]["properties"]["package_version"] = package_version
    (run_dir / "all_tests.json").write_text(json.dumps(run))
    tr.add(run_dir, stream=stream)
    return next(
        d
        for d in (tmp_path / "test_logs").iterdir()
        if d.is_dir() and date in d.name and not d.is_symlink()
    )


def test_get_latest_reads_only_the_newest_run(tmp_path, monkeypatch):
    """Hundreds of indexed runs must not be parsed to answer "the latest"."""
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path))
    _ingest(tmp_path, "ska3-masters", "2026:07:11T00:00:00", "1.0.0")
    _ingest(tmp_path, "ska3-masters", "2026:07:12T00:00:00", "2.0.0")

    reads = []
    real_read = tr._read_run

    def counting_read(entry):
        reads.append(entry["destination"])
        return real_read(entry)

    monkeypatch.setattr(tr, "_read_run", counting_read)
    latest = tr.get_latest(stream="ska3-masters")
    version = latest["test_suites"][0]["properties"]["package_version"]
    assert version == "2.0.0"
    assert len(reads) == 1


def test_get_latest_skips_a_pruned_newest_run(tmp_path, monkeypatch):
    """A pruned run used to make this raise; now the next one down answers."""
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path))
    _ingest(tmp_path, "ska3-masters", "2026:07:11T00:00:00", "1.0.0")
    newest = _ingest(tmp_path, "ska3-masters", "2026:07:12T00:00:00", "2.0.0")
    (newest / "all_tests.json").unlink()

    latest = tr.get_latest(stream="ska3-masters")
    assert latest["test_suites"][0]["properties"]["package_version"] == "1.0.0"


def test_get_skips_pruned_runs(tmp_path, monkeypatch):
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path))
    pruned = _ingest(tmp_path, "ska3-masters", "2026:07:11T00:00:00", "1.0.0")
    _ingest(tmp_path, "ska3-masters", "2026:07:12T00:00:00", "2.0.0")
    (pruned / "all_tests.json").unlink()

    results = tr.get(stream="ska3-masters")
    assert len(results) == 1
    assert results[0]["test_suites"][0]["properties"]["package_version"] == "2.0.0"


def test_get_latest_with_nothing_readable(tmp_path, monkeypatch):
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path))
    only = _ingest(tmp_path, "ska3-masters", "2026:07:12T00:00:00", "1.0.0")
    (only / "all_tests.json").unlink()
    assert tr.get_latest(stream="ska3-masters") == {}


def _days_ago(days):
    """A date as testr writes it, the given number of days in the past."""
    return (datetime.now() - timedelta(days=days)).strftime("%Y:%m:%dT%H:%M:%S")


def test_remove_older_than_prunes_by_the_testr_date(tmp_path, monkeypatch):
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path))
    old = _ingest(tmp_path, "ska3-masters", _days_ago(40), "1.0.0")
    recent = _ingest(tmp_path, "ska3-masters", _days_ago(2), "2.0.0")

    tr.remove_older_than(30)

    assert not old.exists()
    assert recent.exists()
    results = tr.get(stream="ska3-masters")
    versions = [r["test_suites"][0]["properties"]["package_version"] for r in results]
    assert versions == ["2.0.0"]


def test_remove_older_than_ages_out_an_already_pruned_run(tmp_path, monkeypatch):
    """The index outlives its runs, so a missing directory is not an error."""
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path))
    gone = _ingest(tmp_path, "ska3-masters", _days_ago(40), "1.0.0")
    shutil.rmtree(gone)

    tr.remove_older_than(30)

    assert tr.streams() == set()


def test_remove_older_than_leaves_an_undatable_entry_alone(tmp_path, monkeypatch):
    """Refusing to prune is safe; deleting on a guess is not."""
    monkeypatch.setitem(CONFIG, "data_dir", str(tmp_path))
    _ingest(tmp_path, "ska3-masters", _days_ago(40), "1.0.0")
    index_file = tmp_path / "test_logs" / "index.json"
    index = json.loads(index_file.read_text())
    index[0]["destination"] = "renamed_by_hand"
    index_file.write_text(json.dumps(index))

    tr.remove_older_than(30)

    assert json.loads(index_file.read_text()) == index
