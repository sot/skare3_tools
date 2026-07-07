"""
Test bootstrap.

Order matters: skare3_tools.config writes config.json at import, github.py
creates a module-level GithubAPI at import (live GET if a token is present),
and json_cache resolves its directory from CONFIG["data_dir"] at import.
So: set SKARE3_TOOLS_DATA and scrub tokens BEFORE the first skare3_tools import.
"""

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="skare3-tools-tests-")
os.environ["SKARE3_TOOLS_DATA"] = _TMP
os.environ.pop("GITHUB_TOKEN", None)
os.environ.pop("GITHUB_API_TOKEN", None)

import requests  # noqa: E402

# skare3_tools.github builds module-level GithubAPI objects at *import* time
# (github.py:1359, graphql.py:451). Constructing the REST one with no token drops
# into the basic-auth path and fires a live, unauthenticated GET api.github.com/
# during import -- which needs the network (breaks offline) and emits requests'
# HTTPBasicAuth(None, None) DeprecationWarnings. We cannot change production code,
# so we short-circuit requests.request for the duration of the first import only.
# Every request the tests actually care about is stubbed per-test with `responses`
# below; this shim covers *only* the unavoidable import-time calls.
_real_request = requests.request


class _StubResponse:
    status_code = 200
    ok = True
    reason = "OK"
    content = b"{}"

    def json(self):
        return {}


requests.request = lambda *a, **k: _StubResponse()
try:
    import shutil  # noqa: E402
    from pathlib import Path  # noqa: E402

    import pytest  # noqa: E402
    import responses  # noqa: E402

    from skare3_tools import packages  # noqa: E402
    from skare3_tools.config import CONFIG  # noqa: E402
    from skare3_tools.github import github  # noqa: E402
finally:
    requests.request = _real_request


@pytest.fixture()
def data_dir():
    """The test data dir (== CONFIG['data_dir'])."""
    return Path(CONFIG["data_dir"])


@pytest.fixture()
def fake_skare3_repo(monkeypatch, data_dir):
    """Seed pkg_defs fixtures where packages.py expects the skare3 clone."""
    src = Path(__file__).parent / "data" / "pkg_defs"
    dest = data_dir / "skare3" / "pkg_defs"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    monkeypatch.setattr(packages, "_ensure_skare3_local_repo", lambda update=True: None)
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
