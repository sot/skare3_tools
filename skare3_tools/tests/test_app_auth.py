import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import responses
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture()
def app_key(tmp_path, monkeypatch):
    """Generate a throwaway RSA key, point SKARE3_GITHUB_APP_KEY at it."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = tmp_path / "app.pem"
    key_file.write_bytes(pem)
    monkeypatch.setenv("SKARE3_GITHUB_APP_KEY", str(key_file))
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return key_file, public_pem


def test_github_app_token_is_valid_jwt(app_key):
    from skare3_tools.github import app_auth

    token = app_auth.github_app_token()
    assert isinstance(token, str)
    _, public_pem = app_key
    payload = jwt.decode(token, public_pem, algorithms=["RS256"])
    # PyJWT >= 2.10 requires "iss" to be encoded as a string; APP_ID itself
    # stays an int constant, so compare against its string form.
    assert payload["iss"] == str(app_auth.APP_ID)
    assert payload["exp"] - payload["iat"] == 600
    assert abs(payload["iat"] - time.time()) < 60


def test_github_app_token_no_key_raises(monkeypatch):
    from skare3_tools.github import app_auth

    monkeypatch.delenv("SKARE3_GITHUB_APP_KEY", raising=False)
    with pytest.raises(ValueError, match="SKARE3_GITHUB_APP_KEY"):
        app_auth.github_app_token()


@responses.activate
def test_get_installation_token(app_key):
    from skare3_tools.github import app_auth

    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/11316003/access_tokens",
        json={"token": "ghs_testtoken", "expires_at": "2099-01-01T00:00:00Z"},
        status=201,
    )
    result = app_auth.get_installation_token(11316003)
    assert result["token"] == "ghs_testtoken"
    auth_header = responses.calls[0].request.headers["Authorization"]
    assert auth_header.startswith("Bearer ")


def test_app_settings(monkeypatch):
    from skare3_tools.github import app_auth

    monkeypatch.setenv("SKARE3_GITHUB_APP_KEY", "/some/key.pem")
    monkeypatch.setenv("SKARE3_GITHUB_APP_ORG", "sot")
    assert app_auth.app_settings() == {
        "app_id": app_auth.APP_ID,
        "key_path": "/some/key.pem",
        "org": "sot",
    }


def test_app_settings_unset(monkeypatch):
    from skare3_tools.github import app_auth

    monkeypatch.delenv("SKARE3_GITHUB_APP_KEY", raising=False)
    monkeypatch.delenv("SKARE3_GITHUB_APP_ORG", raising=False)
    settings = app_auth.app_settings()
    assert settings["key_path"] is None
    assert settings["org"] is None


@responses.activate
def test_get_installations(app_key):
    from skare3_tools.github import app_auth

    responses.add(
        responses.GET,
        "https://api.github.com/app/installations",
        json=[{"id": 11316003, "account": {"login": "sot"}}],
        status=200,
    )
    result = app_auth.get_installations()
    assert result[0]["id"] == 11316003
    auth_header = responses.calls[0].request.headers["Authorization"]
    assert auth_header.startswith("Bearer ")


def test_resolve_token_argument_wins(monkeypatch):
    from skare3_tools.github.github import resolve_token

    monkeypatch.setenv("GITHUB_API_TOKEN", "ghp_env")
    assert resolve_token("ghp_arg") == "ghp_arg"


def test_resolve_token_from_env(monkeypatch):
    from skare3_tools.github.github import resolve_token

    monkeypatch.setenv("GITHUB_API_TOKEN", "ghp_api")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_plain")
    assert resolve_token() == "ghp_api"
    monkeypatch.delenv("GITHUB_API_TOKEN")
    assert resolve_token() == "ghp_plain"


def test_resolve_token_none_without_credentials(app_key, monkeypatch):
    from skare3_tools.github.github import resolve_token

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_API_TOKEN", raising=False)
    # an App key alone does not make resolve_token return a token;
    # App auth is handled by the callers via AppTokenCache
    assert resolve_token() is None


def _stub_installation(org, installation_id):
    responses.add(
        responses.GET,
        f"https://api.github.com/orgs/{org}/installation",
        json={"id": installation_id, "account": {"login": org}},
        status=200,
    )


def _stub_mint(installation_id, token, expires_in=3600):
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    responses.add(
        responses.POST,
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        json={
            "token": token,
            "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        status=201,
    )


@responses.activate
def test_token_cache_per_org(app_key):
    from skare3_tools.github import app_auth

    _stub_installation("sot", 1)
    _stub_installation("acisops", 2)
    _stub_mint(1, "ghs_sot")
    _stub_mint(2, "ghs_acisops")
    cache = app_auth.AppTokenCache()
    assert cache.token("sot") == "ghs_sot"
    assert cache.token("acisops") == "ghs_acisops"
    assert cache.token("sot") == "ghs_sot"  # cached: no extra requests
    assert len(responses.calls) == 4  # 2 lookups + 2 mints


@responses.activate
def test_token_cache_reminits_near_expiry(app_key):
    from skare3_tools.github import app_auth

    _stub_installation("sot", 1)
    _stub_mint(1, "ghs_first", expires_in=120)  # within the 300 s margin
    cache = app_auth.AppTokenCache()
    assert cache.token("sot") == "ghs_first"
    responses.add(  # next mint returns a fresh token
        responses.POST,
        "https://api.github.com/app/installations/1/access_tokens",
        json={
            "token": "ghs_second",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        },
        status=201,
    )
    assert cache.token("sot") == "ghs_second"


@responses.activate
def test_token_cache_default_org_from_env(app_key, monkeypatch):
    from skare3_tools.github import app_auth

    monkeypatch.setenv("SKARE3_GITHUB_APP_ORG", "sot")
    _stub_installation("sot", 1)
    _stub_mint(1, "ghs_sot")
    assert app_auth.AppTokenCache().token() == "ghs_sot"


@responses.activate
def test_token_cache_default_org_single_installation(app_key, monkeypatch):
    from skare3_tools.github import app_auth

    monkeypatch.delenv("SKARE3_GITHUB_APP_ORG", raising=False)
    responses.add(
        responses.GET,
        "https://api.github.com/app/installations",
        json=[{"id": 1, "account": {"login": "sot"}}],
        status=200,
    )
    _stub_installation("sot", 1)
    _stub_mint(1, "ghs_sot")
    assert app_auth.AppTokenCache().token() == "ghs_sot"


@responses.activate
def test_token_cache_default_org_ambiguous(app_key, monkeypatch):
    from skare3_tools.github import app_auth
    from skare3_tools.github.github import AuthException

    monkeypatch.delenv("SKARE3_GITHUB_APP_ORG", raising=False)
    responses.add(
        responses.GET,
        "https://api.github.com/app/installations",
        json=[
            {"id": 1, "account": {"login": "sot"}},
            {"id": 2, "account": {"login": "acisops"}},
        ],
        status=200,
    )
    with pytest.raises(AuthException, match="SKARE3_GITHUB_APP_ORG"):
        app_auth.AppTokenCache().token()


@responses.activate
def test_token_cache_user_account(app_key):
    from skare3_tools.github import app_auth

    responses.add(
        responses.GET,
        "https://api.github.com/orgs/javierggt/installation",
        json={"message": "Not Found"},
        status=404,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/users/javierggt/installation",
        json={"id": 3, "account": {"login": "javierggt"}},
        status=200,
    )
    _stub_mint(3, "ghs_user")
    assert app_auth.AppTokenCache().token("javierggt") == "ghs_user"


@responses.activate
def test_token_cache_uncovered_org_message(app_key):
    from skare3_tools.github import app_auth
    from skare3_tools.github.github import AuthException

    for account_type in ["orgs", "users"]:
        responses.add(
            responses.GET,
            f"https://api.github.com/{account_type}/cxc-ops/installation",
            json={"message": "Not Found"},
            status=404,
        )
    responses.add(
        responses.GET,
        "https://api.github.com/app/installations",
        json=[
            {"id": 1, "account": {"login": "sot"}},
            {"id": 2, "account": {"login": "acisops"}},
        ],
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/app",
        json={"slug": "skare3", "name": "skare3"},
        status=200,
    )
    with pytest.raises(AuthException) as err:
        app_auth.AppTokenCache().token("cxc-ops")
    message = str(err.value)
    assert "cannot access 'cxc-ops'" in message
    assert "acisops, sot" in message
    assert "https://github.com/apps/skare3/installations/new" in message
    assert "GITHUB_TOKEN" in message


def test_org_from_endpoint():
    from skare3_tools.github.github import _org_from_endpoint

    assert _org_from_endpoint("repos/sot/skare3/releases") == "sot"
    assert _org_from_endpoint("orgs/acisops/repos") == "acisops"
    assert _org_from_endpoint("users/javierggt/repos") == "javierggt"
    assert _org_from_endpoint("rate_limit") is None
    assert _org_from_endpoint("") is None
    assert _org_from_endpoint("repos") is None


@responses.activate
def test_rest_uses_per_org_tokens(app_key, monkeypatch):
    from skare3_tools.github import github

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_API_TOKEN", raising=False)
    monkeypatch.setenv("SKARE3_GITHUB_APP_ORG", "sot")
    _stub_installation("sot", 1)
    _stub_installation("acisops", 2)
    _stub_mint(1, "ghs_sot")
    _stub_mint(2, "ghs_acisops")
    responses.add(responses.GET, "https://api.github.com/", json={}, status=200)
    responses.add(
        responses.GET,
        "https://api.github.com/user",
        json={"message": "Resource not accessible by integration"},
        status=403,
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/acisops/foo",
        json={"name": "foo"},
        status=200,
    )
    api = github.GithubAPI()
    assert api.initialized
    api.get("/repos/acisops/foo")
    auth_by_url = {
        call.request.url: call.request.headers.get("Authorization")
        for call in responses.calls
    }
    # org-less init requests use the default (sot) token
    assert auth_by_url["https://api.github.com/"] == "token ghs_sot"
    # the acisops repo request uses the acisops token
    assert (
        auth_by_url["https://api.github.com/repos/acisops/foo"] == "token ghs_acisops"
    )


@responses.activate
def test_rest_init_env_token_wins_over_app_key(app_key, monkeypatch):
    from skare3_tools.github import github

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_env")
    monkeypatch.setenv("SKARE3_GITHUB_APP_ORG", "sot")
    responses.add(responses.GET, "https://api.github.com/", json={}, status=200)
    responses.add(
        responses.GET,
        "https://api.github.com/user",
        json={"login": "tester"},
        status=200,
    )
    api = github.GithubAPI()
    assert api.headers["Authorization"] == "token ghp_env"
    assert api._app_tokens is None
    urls = [call.request.url for call in responses.calls]
    assert not any("installation" in url for url in urls)
