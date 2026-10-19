import hashlib
import hmac
from types import SimpleNamespace

import pytest

from app.services import github_app


def test_webhook_signature_is_verified(monkeypatch):
    monkeypatch.setattr(
        github_app,
        "settings",
        lambda: SimpleNamespace(github_webhook_secret="test-secret"),
    )
    body = b'{"zen":"secure"}'
    signature = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    github_app.verify_webhook_signature(body, signature)
    with pytest.raises(ValueError, match="Invalid GitHub webhook signature"):
        github_app.verify_webhook_signature(body, "sha256=wrong")


def test_installation_token_uses_signed_github_app_assertion(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        github_app,
        "settings",
        lambda: SimpleNamespace(
            github_app_id="123",
            github_app_private_key="private\\nkey",
            github_token="fallback",
        ),
    )
    monkeypatch.setattr(
        github_app.jwt,
        "encode",
        lambda claims, key, algorithm: captured.update(
            claims=claims, key=key, algorithm=algorithm
        )
        or "signed-assertion",
    )

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {"token": "installation-token"}

    def post(url, **kwargs):
        captured.update(url=url, request=kwargs)
        return Response()

    monkeypatch.setattr(github_app.httpx, "post", post)
    assert github_app.installation_token(42) == "installation-token"
    assert captured["url"].endswith("/app/installations/42/access_tokens")
    assert captured["key"] == "private\nkey"
    assert captured["algorithm"] == "RS256"
    assert captured["request"]["headers"]["Authorization"] == "Bearer signed-assertion"


def test_commit_status_uses_stable_context(monkeypatch):
    captured = {}

    class Response:
        status_code = 201

    monkeypatch.setattr(
        github_app.httpx,
        "post",
        lambda url, **kwargs: captured.update(url=url, request=kwargs) or Response(),
    )
    github_app.publish_commit_status("acme", "shop", "abc123", "success", "Complete", "token")
    assert captured["url"].endswith("/repos/acme/shop/statuses/abc123")
    assert captured["request"]["json"]["context"] == "Regora / PR Guardian"
    assert captured["request"]["json"]["state"] == "success"
