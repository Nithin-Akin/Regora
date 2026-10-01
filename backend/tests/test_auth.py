from hashlib import sha256
import hmac
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.security.auth as auth


SECRET = "a-secure-shared-secret-with-32-characters"


@pytest.fixture
def github_auth(monkeypatch):
    config = SimpleNamespace(
        auth_mode="github",
        auth_shared_secret=SECRET,
        auth_header_ttl=60,
        github_token="",
    )
    monkeypatch.setattr(auth, "settings", lambda: config)
    return config


def headers(user_id="github:42", timestamp="1000", token="github-token"):
    signature = hmac.new(
        SECRET.encode(),
        auth.signing_payload(timestamp, user_id, token),
        sha256,
    ).hexdigest()
    return {
        "x-regora-user-id": user_id,
        "x-regora-auth-timestamp": timestamp,
        "x-regora-auth-signature": signature,
        "x-regora-github-token": token,
    }


def test_signed_gateway_identity_is_accepted(github_auth):
    user = auth.signed_user(headers(), now=1000)
    assert user.id == "github:42"
    assert user.github_token == "github-token"


def test_tampered_or_expired_identity_is_rejected(github_auth):
    tampered = headers()
    tampered["x-regora-user-id"] = "github:99"
    with pytest.raises(HTTPException, match="Invalid authentication signature"):
        auth.signed_user(tampered, now=1000)
    with pytest.raises(HTTPException, match="Authentication expired"):
        auth.signed_user(headers(), now=1061)


def test_local_mode_uses_isolated_local_owner(monkeypatch):
    monkeypatch.setattr(
        auth,
        "settings",
        lambda: SimpleNamespace(auth_mode="local", github_token="optional-token"),
    )
    assert auth.signed_user({}).id == "local"
