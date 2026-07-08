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
