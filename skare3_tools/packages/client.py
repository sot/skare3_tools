"""
Read access to the package data for every consumer.

``DataClient`` hides where the data comes from:

- ``local`` — the store on disk (``$SKA/data`` sync; no network, no token),
- ``http`` — the published store (``CONFIG["store_url"]``),
- ``github`` — direct queries through the legacy API (needs a token; slow),
- ``auto`` (default) — local if a store is present, else http, falling back
  to github only if the published data is unreachable.
"""

import logging

import requests

from skare3_tools.config import CONFIG
from skare3_tools.packages import packages, store

logger = logging.getLogger("skare3.client")


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
        if source == "auto":
            source = "local" if store.store_present(data_dir) else "http"
        self.source = source
        logger.info("reading package data from source=%s", self.source)

    def packages(self):
        """The aggregate the dashboard consumes (packages.json)."""
        if self.source == "local":
            return store.StoreReader(self.data_dir).packages()
        if self.source == "http":
            try:
                return self._get_json("packages.json")
            except requests.RequestException as exc:
                logger.warning(
                    "published data unreachable (%s), querying GitHub directly", exc
                )
                self.source = "github"
        return packages.get_repositories_info()

    def test_results(self):
        """The digested latest test results (test_results.json)."""
        if self.source == "local":
            return store.StoreReader(self.data_dir).test_results()
        return self._get_json("test_results.json")

    def repository_info(self, owner_repo):
        """Detailed information for one repository."""
        if self.source == "local":
            return store.StoreReader(self.data_dir).repository_info(owner_repo)
        if self.source == "http":
            r = requests.get(f"{self.url}/repos/{owner_repo}.json")
            if r.ok:
                return r.json()
            # per-repo files may not be published: use the aggregate entry
            owner, name = owner_repo.split("/")
            for pkg in self.packages()["packages"]:
                if pkg["owner"] == owner and pkg["name"] == name:
                    return pkg
            raise KeyError(f"{owner_repo} not in the published data")
        return packages.get_repository_info(owner_repo)

    def _get_json(self, name):
        r = requests.get(f"{self.url}/{name}")
        r.raise_for_status()
        return r.json()
