"""
Data-store primitives (skare3_tools/packages/store.py).

Behavior pinned:
- The store root is CONFIG["data_dir"]; a store is present iff manifest.json
  is readable there.
- atomic_write_json leaves no temp file behind and replaces content whole.
- StoreLock is exclusive: a second acquisition raises StoreLockedError.
- StoreReader reads the store files and rejects a store written with a newer
  schema than this code understands.
- repository_status returns {} when the file is absent and fails loudly on an
  unknown status value.
"""

import json
import os
from pathlib import Path

import pytest

from skare3_tools.packages import store


@pytest.fixture()
def store_dir(data_dir):
    """A clean store root (== CONFIG['data_dir'], see conftest)."""
    names = (
        "manifest.json",
        "packages.json",
        "test_results.json",
        "repository_status.json",
    )
    for name in names:
        path = data_dir / name
        if path.exists():
            path.unlink()
    return data_dir


def _write_manifest(store_dir, **kwargs):
    manifest = {
        "schema_version": store.SCHEMA_VERSION,
        "generated": "2026-07-13T00:00:00",
    }
    manifest.update(kwargs)
    (store_dir / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_store_dir_is_config_data_dir(store_dir):
    assert store.store_dir() == Path(store_dir)


def test_atomic_write_json(store_dir):
    path = store_dir / "packages.json"
    store.atomic_write_json(path, {"packages": []})
    assert json.loads(path.read_text()) == {"packages": []}
    leftovers = [f for f in os.listdir(store_dir) if "tmp" in f]
    assert leftovers == []


def test_store_present_requires_manifest(store_dir):
    assert not store.store_present(store_dir)
    _write_manifest(store_dir)
    assert store.store_present(store_dir)


def test_lock_is_exclusive(store_dir):
    with store.StoreLock(store_dir):
        with pytest.raises(store.StoreLockedError):
            with store.StoreLock(store_dir):
                pass
    # released: can be taken again
    with store.StoreLock(store_dir):
        pass


def test_reader_round_trip(store_dir):
    manifest = _write_manifest(store_dir)
    store.atomic_write_json(
        store_dir / "packages.json", {"packages": [{"name": "kadi"}]}
    )
    store.atomic_write_json(store_dir / "test_results.json", {"test_suites": []})
    store.atomic_write_json(
        store_dir / "repos" / "sot" / "kadi.json", {"name": "kadi", "owner": "sot"}
    )
    reader = store.StoreReader(store_dir)
    assert reader.manifest() == manifest
    assert reader.packages()["packages"][0]["name"] == "kadi"
    assert reader.test_results() == {"test_suites": []}
    assert reader.repository_info("sot/kadi")["owner"] == "sot"


def test_reader_missing_store_raises(store_dir):
    with pytest.raises(store.StoreNotFoundError):
        store.StoreReader(store_dir)


def test_repository_status(store_dir):
    assert store.repository_status(store_dir) == {}
    status = {"sot/skare": "deprecated", "sot/test-actions": "ignored"}
    (store_dir / "repository_status.json").write_text(json.dumps(status))
    assert store.repository_status(store_dir) == status


def test_repository_status_rejects_unknown_status(store_dir):
    (store_dir / "repository_status.json").write_text(
        json.dumps({"sot/skare": "deprectaed"})
    )
    with pytest.raises(ValueError, match="deprectaed"):
        store.repository_status(store_dir)


def test_reader_rejects_newer_schema(store_dir):
    _write_manifest(store_dir, schema_version=store.SCHEMA_VERSION + 1)
    with pytest.raises(store.StoreNotFoundError):
        store.StoreReader(store_dir)
