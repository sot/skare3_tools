import time

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


@responses.activate
def test_get_installation_token_id_from_env(app_key, monkeypatch):
    from skare3_tools.github import app_auth

    monkeypatch.setenv("SKARE3_GITHUB_APP_INSTALLATION", "11316003")
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/11316003/access_tokens",
        json={"token": "ghs_testtoken", "expires_at": "2099-01-01T00:00:00Z"},
        status=201,
    )
    result = app_auth.get_installation_token()
    assert result["token"] == "ghs_testtoken"


def test_get_installation_token_no_id_raises(app_key, monkeypatch):
    from skare3_tools.github import app_auth

    monkeypatch.delenv("SKARE3_GITHUB_APP_INSTALLATION", raising=False)
    with pytest.raises(ValueError, match="SKARE3_GITHUB_APP_INSTALLATION"):
        app_auth.get_installation_token()


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


def test_resolve_token_env_wins_over_app_key(app_key, monkeypatch):
    from skare3_tools.github.github import resolve_token

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_env")
    monkeypatch.setenv("SKARE3_GITHUB_APP_INSTALLATION", "11316003")
    assert resolve_token() == "ghp_env"


def test_resolve_token_key_without_installation_is_none(app_key, monkeypatch):
    from skare3_tools.github.github import resolve_token

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_API_TOKEN", raising=False)
    monkeypatch.delenv("SKARE3_GITHUB_APP_INSTALLATION", raising=False)
    assert resolve_token() is None


@responses.activate
def test_rest_init_falls_back_to_app_token(app_key, monkeypatch):
    from skare3_tools.github import github

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_API_TOKEN", raising=False)
    monkeypatch.setenv("SKARE3_GITHUB_APP_INSTALLATION", "11316003")
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/11316003/access_tokens",
        json={"token": "ghs_apptoken", "expires_at": "2099-01-01T00:00:00Z"},
        status=201,
    )
    responses.add(responses.GET, "https://api.github.com/", json={}, status=200)
    responses.add(
        responses.GET,
        "https://api.github.com/user",
        json={"login": "skare3[bot]"},
        status=200,
    )
    api = github.GithubAPI()
    assert api.initialized
    assert api.headers["Authorization"] == "token ghs_apptoken"


@responses.activate
def test_rest_init_env_token_wins_over_app_key(app_key, monkeypatch):
    from skare3_tools.github import github

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_env")
    monkeypatch.setenv("SKARE3_GITHUB_APP_INSTALLATION", "11316003")
    responses.add(responses.GET, "https://api.github.com/", json={}, status=200)
    responses.add(
        responses.GET,
        "https://api.github.com/user",
        json={"login": "tester"},
        status=200,
    )
    api = github.GithubAPI()
    assert api.headers["Authorization"] == "token ghp_env"
    urls = [call.request.url for call in responses.calls]
    assert not any("access_tokens" in url for url in urls)


@responses.activate
def test_graphql_init_falls_back_to_app_token(app_key, monkeypatch):
    from skare3_tools.github import graphql

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_API_TOKEN", raising=False)
    monkeypatch.setenv("SKARE3_GITHUB_APP_INSTALLATION", "11316003")
    responses.add(
        responses.POST,
        "https://api.github.com/app/installations/11316003/access_tokens",
        json={"token": "ghs_apptoken", "expires_at": "2099-01-01T00:00:00Z"},
        status=201,
    )
    responses.add(
        responses.POST,
        "https://api.github.com/graphql",
        json={"data": {"viewer": {"login": "skare3[bot]"}}},
        status=200,
    )
    api = graphql.GithubAPI()
    api.init()
    assert api.initialized
    assert api.headers["Authorization"] == "token ghs_apptoken"
