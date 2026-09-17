"""
Read access to the package data for every consumer.

``DataClient`` hides where the data comes from:

- ``local`` — the store on disk (``$SKA/data`` sync; no network, no token),
- ``http`` — the published store (``CONFIG["store_url"]``),
- ``github`` — direct queries through the legacy API (needs a token; slow),
- ``auto`` (default) — local if a store is present, else http, falling back
  to github only if the published data is unreachable.

Falling back is decided per file, not once for the client: a store or a
published location can be missing one file and authoritative for the rest,
which is exactly what a store written by an older layout looks like. Getting
this wrong is expensive — one absent file would send every other read to
GitHub.

What a client reads is remembered for its lifetime, so picking many
repositories out of the aggregate costs one read. Build a new client to see
newer data.
"""

import json
import logging

import requests

from skare3_tools.config import CONFIG
from skare3_tools.packages import packages, store

logger = logging.getLogger("skare3.client")

# a source that raises one of these has not got the file (missing, unreadable
# or corrupt); try the next one. Anything else is a real error and propagates.
_NOT_AVAILABLE = (
    OSError,
    json.JSONDecodeError,
    store.StoreNotFoundError,
    requests.RequestException,
)


class DataClient:
    """
    Read package data from the best available source.

    :param source: "auto", "local", "http" or "github".
    :param data_dir: local store directory (default: the configured root).
    :param url: published store URL (default: CONFIG["store_url"]).
    """

    def __init__(self, source="auto", data_dir=None, url=None):
        self.data_dir = data_dir
        self.url = url or CONFIG.get("store_url")
        self.source = source
        self._read = {}
        logger.info("reading package data from source=%s", self.source)

    def packages(self):
        """The aggregate: every repository's record, plus the channel versions."""
        return self._once(
            "packages.json",
            {
                "local": lambda: store.StoreReader(self.data_dir).packages(),
                "http": lambda: self._get_json("packages.json"),
                "github": packages._repositories_info_from_github,
            },
        )

    def package_list(self):
        """The package universe, as :func:`~skare3_tools.packages.get_package_list`."""
        return self._once(
            "package_list.json",
            {
                "local": lambda: store.StoreReader(self.data_dir).package_list(),
                "http": lambda: self._get_json("package_list.json")["package_list"],
                "github": packages._package_list_from_github,
            },
        )

    def test_results(self):
        """The digested latest test results (test_results.json)."""
        return self._once(
            "test_results.json",
            {
                "local": lambda: store.StoreReader(self.data_dir).test_results(),
                "http": lambda: self._get_json("test_results.json"),
                # no github entry: test results exist only in the store, so the
                # chain ends at http and its error is the one worth reporting
            },
        )

    def repository_info(self, owner_repo):
        """
        Detailed information for one repository.

        The aggregate holds the only copy of each record, so this picks the
        entry out of it -- identically for every source.
        """
        return store.repository_entry(self.packages(), owner_repo)

    def generated(self):
        """When the data was produced (ISO string), or "" if it does not say."""
        return store.generated(self.packages())

    def sources(self):
        """The sources to try, in order, for this client's configured source."""
        if self.source == "auto":
            if store.store_present(self.data_dir):
                return ("local", "http", "github")
            return ("http", "github")
        if self.source == "http":
            return ("http", "github")
        return (self.source,)

    def _fetch(self, name, readers):
        """Read ``name`` from the first source that has it."""
        sources = [source for source in self.sources() if source in readers]
        if not sources:
            raise store.StoreNotFoundError(
                f"{name} cannot be read from source={self.source}"
            )
        for source, following in zip(sources, sources[1:], strict=False):
            try:
                return readers[source]()
            except _NOT_AVAILABLE as exc:
                logger.info(
                    "no %s from source=%s (%s); trying %s", name, source, exc, following
                )
        return readers[sources[-1]]()

    def _once(self, name, readers):
        if name not in self._read:
            self._read[name] = self._fetch(name, readers)
        return self._read[name]

    def _get_json(self, name):
        r = requests.get(f"{self.url}/{name}")
        r.raise_for_status()
        try:
            return r.json()
        except json.JSONDecodeError as exc:
            # a misconfigured location can serve an error page with status 200
            raise requests.RequestException(f"{self.url}/{name} is not JSON") from exc
