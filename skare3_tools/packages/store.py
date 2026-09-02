"""
The consolidated package-data store.

One producer (``skare3-refresh``) writes these files; everything else reads
them. The store root is ``CONFIG["data_dir"]`` — ``$SKA/data/skare3/skare3_data/data``
on synced hosts — which reaches every machine through the existing ``$SKA/data``
rsync. Layout::

    <data_dir>/
    ├── manifest.json          # schema_version, generated, producer, excluded
    ├── repository_status.json # operator-edited: {owner/repo: "deprecated"|"ignored"}
    ├── packages.json          # the per-repository records (the only copy) + channel state
    ├── package_list.json      # the package universe (pkg_defs + org repos), unfiltered
    ├── test_results.json      # pre-digested latest test results
    ├── test_logs/             # test-results runs (see test_results.py)
    └── meta/
        ├── state.json         # producer bookkeeping (last-updated timestamps)
        └── refresh.lock

``packages.json`` holds each repository's record exactly once: there is no
separate per-repository tree to drift out of sync with it. Single-repository
reads pick the entry out of the aggregate (see :class:`StoreReader`).

Every file is written atomically (temp file + ``os.replace``), so readers on
rsync'd copies never see a half-written file. Readers never take the lock.

``repository_status.json`` is the one file the producer reads rather than
writes: repositories listed there (with either status) are excluded from the
store. The first refresh seeds it if absent; after that it is never overwritten.
"""

import fcntl
import json
import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

from skare3_tools.config import CONFIG

# the store layout: which files exist and how a reader finds things in them.
# Bumping this makes readers of other versions decline the store.
SCHEMA_VERSION = 3

# the shape of a single repository record inside packages.json. Bump this when
# the fields of a record change, which is what makes already-stored records
# unusable and forces the producer to refetch them. It is deliberately separate
# from SCHEMA_VERSION: rearranging which files the store has does not make the
# records in it any less valid.
RECORD_VERSION = 1

# statuses an operator may assign in repository_status.json; any repo listed
# (with either status) is excluded from the store
REPOSITORY_STATUSES = ("deprecated", "ignored")

logger = logging.getLogger("skare3.store")


class StoreNotFoundError(Exception):
    """There is no (readable, compatible) store at the given location."""


class StoreLockedError(Exception):
    """Another producer holds the refresh lock."""


def store_dir():
    """The store root: CONFIG["data_dir"]."""
    return Path(CONFIG["data_dir"])


def store_present(directory=None):
    """
    True if there is a store at ``directory`` that this code can read.

    A store written by a *newer* schema counts as absent: this code does not
    know its layout. An older one counts as present -- a layout change adds and
    removes files, so a reader takes what is there and looks elsewhere for the
    rest.
    """
    directory = Path(directory) if directory else store_dir()
    try:
        manifest = _read_json(directory / "manifest.json")
    except (OSError, json.JSONDecodeError):
        return False
    return manifest.get("schema_version", 0) <= SCHEMA_VERSION


def repository_status(directory=None):
    """The operator-edited status map ({owner/repo: status}); {} if the file is absent."""
    directory = Path(directory) if directory else store_dir()
    try:
        status = _read_json(directory / "repository_status.json")
    except FileNotFoundError:
        return {}
    unknown = {
        repo: value
        for repo, value in status.items()
        if value not in REPOSITORY_STATUSES
    }
    if unknown:
        raise ValueError(
            f"repository_status.json: unknown status for {unknown}; "
            f"allowed: {REPOSITORY_STATUSES}"
        )
    return status


def atomic_write_json(path, obj):
    """Write JSON so readers only ever see the old or the new content."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=1)
    os.replace(tmp, path)


def _read_json(path):
    with open(path) as fh:
        return json.load(fh)


class StoreLock:
    """
    Exclusive single-writer lock on the store (meta/refresh.lock).

    Raises StoreLockedError immediately on contention; the lock file records
    who holds it.
    """

    def __init__(self, directory=None):
        self.path = (
            (Path(directory) if directory else store_dir()) / "meta" / "refresh.lock"
        )
        self._fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.seek(0)
            holder = self._fh.read().strip()
            self._fh.close()
            self._fh = None
            raise StoreLockedError(
                f"store is locked by {holder or 'unknown'}"
            ) from None
        self._fh.truncate(0)
        self._fh.write(
            f"pid {os.getpid()} on {socket.gethostname()} "
            f"since {datetime.now(timezone.utc).isoformat()}"
        )
        self._fh.flush()
        return self

    def __exit__(self, *exc_info):
        fcntl.flock(self._fh, fcntl.LOCK_UN)
        self._fh.close()
        self._fh = None


class StoreReader:
    """Read-only access to a store directory."""

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else store_dir()
        try:
            self._manifest = _read_json(self.directory / "manifest.json")
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreNotFoundError(f"no data store at {self.directory}") from exc
        version = self._manifest.get("schema_version", 0)
        if version > SCHEMA_VERSION:
            raise StoreNotFoundError(
                f"store at {self.directory} has schema {version}, newer than "
                f"this skare3_tools ({SCHEMA_VERSION}); update skare3_tools"
            )
        if version < SCHEMA_VERSION:
            # an older layout may be missing files this code reads, but the
            # files it does have are still good: let each read decide. A
            # missing one raises FileNotFoundError, which is what a caller
            # needs to look elsewhere for that file alone.
            logger.info(
                "store at %s has schema %s, older than this skare3_tools (%s): "
                "reading what it has",
                self.directory,
                version,
                SCHEMA_VERSION,
            )

    def manifest(self):
        return self._manifest

    def packages(self):
        return _read_json(self.directory / "packages.json")

    def package_list(self):
        """The package universe as ``get_package_list`` returns it (a list)."""
        return _read_json(self.directory / "package_list.json")["package_list"]

    def test_results(self):
        return _read_json(self.directory / "test_results.json")

    def repository_info(self, owner_repo):
        """One repository's record, taken from the aggregate (its only copy)."""
        return repository_entry(self.packages(), owner_repo)


def repository_entry(aggregate, owner_repo):
    """
    Pick one repository's record out of an aggregate (``packages.json``).

    :param aggregate: dict. The parsed aggregate.
    :param owner_repo: str. e.g. "sot/chandra_aca".
    :raises KeyError: if the aggregate has no entry for that repository.
    """
    owner, name = owner_repo.split("/")
    for pkg in aggregate["packages"]:
        if pkg["owner"] == owner and pkg["name"] == name:
            return pkg
    raise KeyError(f"{owner_repo} is not in the package data")


def generated(aggregate):
    """
    When the aggregate was produced (ISO string), or "" if it does not say.

    This is the staleness signal available to every reader: ``manifest.json``
    is deliberately not published, so the aggregate's own timestamp is all an
    HTTP reader gets.
    """
    return aggregate.get("time", "")
