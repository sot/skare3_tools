"""
The test-results store (skare3_tools/test_results.py).

Behavior pinned:
- add()/get()/get_latest()/streams() round-trip through the store at
  CONFIG["data_dir"]/test_logs, resolved lazily at call time (no
  import-time directory creation), so the producer can point it anywhere.
- A duplicate add is refused; reading a store that was never written raises
  FileNotFoundError (callers treat that as "no results yet").
"""

import json

import pytest

# test_results needs cxotime, which is not pip-installable
# (unavailable in the PR workflow environment)
pytest.importorskip("cxotime")

from skare3_tools import test_results as tr  # noqa: E402
from skare3_tools.config import CONFIG  # noqa: E402

ALL_TESTS = {
    "run_info": {
        "date": "2026-07-12T00:00:00",
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
