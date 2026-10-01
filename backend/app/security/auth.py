"""Authenticate requests forwarded by the trusted Next.js application gateway."""

from dataclasses import dataclass
from hashlib import sha256
import hmac
import re
import time

from fastapi import HTTPException, Request

from app.config import settings


USER_ID = re.compile(r"^(?:local|github:[0-9]+)$")


@dataclass(frozen=True)
class CurrentUser:
    id: str
    github_token: str = ""


def signing_payload(timestamp: str, user_id: str, github_token: str = "") -> bytes:
    token_hash = sha256(github_token.encode()).hexdigest()
    return f"v1:{timestamp}:{user_id}:{token_hash}".encode()


def signed_user(headers, *, now: int | None = None) -> CurrentUser:
    cfg = settings()
    if cfg.auth_mode == "local":
        return CurrentUser("local", cfg.github_token)
    if cfg.auth_mode != "github":
        raise HTTPException(503, "AUTH_MODE must be local or github")
    if len(cfg.auth_shared_secret) < 32:
        raise HTTPException(503, "AUTH_SHARED_SECRET must contain at least 32 characters")

    user_id = headers.get("x-regora-user-id", "")
    timestamp = headers.get("x-regora-auth-timestamp", "")
    signature = headers.get("x-regora-auth-signature", "")
    github_token = headers.get("x-regora-github-token", "")
    if not USER_ID.fullmatch(user_id) or not timestamp.isdigit() or len(github_token) > 1000:
        raise HTTPException(401, "Authentication required")
    current = int(time.time()) if now is None else now
    if abs(current - int(timestamp)) > cfg.auth_header_ttl:
        raise HTTPException(401, "Authentication expired")
    expected = hmac.new(
        cfg.auth_shared_secret.encode(),
        signing_payload(timestamp, user_id, github_token),
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid authentication signature")
    return CurrentUser(user_id, github_token)


def current_user(request: Request) -> CurrentUser:
    return signed_user(request.headers)
