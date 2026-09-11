"""
Test bootstrap.

Order matters: skare3_tools.config writes config.json at import, and github.py
creates a module-level GithubAPI at import (which resolves whatever credentials
are in the environment, without using them). So: set SKARE3_TOOLS_DATA and
scrub tokens BEFORE the first skare3_tools import.
"""

import contextlib
import os
import shutil
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="skare3-tools-tests-")
os.environ["SKARE3_TOOLS_DATA"] = _TMP
os.environ.pop("GITHUB_TOKEN", None)
os.environ.pop("GITHUB_API_TOKEN", None)
os.environ.pop("SKARE3_GITHUB_APP_KEY", None)
os.environ.pop("SKARE3_GITHUB_APP_ORG", None)

import pytest  # noqa: E402
import responses  # noqa: E402

from skare3_tools import packages  # noqa: E402
from skare3_tools.config import CONFIG  # noqa: E402
from skare3_tools.github import github  # noqa: E402


@pytest.fixture()
def data_dir():
    """The test data dir (== CONFIG['data_dir'])."""
    return Path(CONFIG["data_dir"])


@pytest.fixture()
def fake_skare3_repo(monkeypatch, tmp_path):
    """Serve the pkg_defs fixtures instead of fetching the skare3 recipes."""
    dest = tmp_path / "pkg_defs"
    shutil.copytree(Path(__file__).parent / "data" / "pkg_defs", dest)

    @contextlib.contextmanager
    def fixture_recipes():
        yield dest

    # patch the defining module: packages is a subpackage re-exporting it
    monkeypatch.setattr(packages.packages, "_skare3_recipes", fixture_recipes)
    return dest


@pytest.fixture()
def github_api():
    """A GithubAPI with a fake token, built while GET / and /user are stubbed."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, "https://api.github.com/", json={}, status=200)
        rsps.add(
            responses.GET,
            "https://api.github.com/user",
            json={"login": "tester"},
            status=200,
        )
        api = github.GithubAPI(token="test-token")
        yield api, rsps
