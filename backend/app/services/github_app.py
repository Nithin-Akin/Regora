"""Authenticated GitHub App operations for the continuous PR guardian."""

import hmac
import time
from hashlib import sha256

import httpx
import jwt

from app.config import settings

API = "https://api.github.com"


def verify_webhook_signature(body: bytes, signature: str) -> None:
    secret = settings().github_webhook_secret
    if not secret:
        raise RuntimeError("GITHUB_WEBHOOK_SECRET is not configured")
    expected = "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid GitHub webhook signature")


def installation_token(installation_id: int) -> str:
    config = settings()
    if config.github_app_id and config.github_app_private_key:
        now = int(time.time())
        assertion = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": config.github_app_id},
            config.github_app_private_key.replace("\\n", "\n"),
            algorithm="RS256",
        )
        response = httpx.post(
            f"{API}/app/installations/{installation_id}/access_tokens",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {assertion}",
                "User-Agent": "Regora",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20,
        )
        if response.status_code != 201:
            raise RuntimeError("GitHub App installation authentication failed")
        token = response.json().get("token", "")
        if not token:
            raise RuntimeError("GitHub did not return an installation token")
        return token
    if config.github_token:
        return config.github_token
    raise RuntimeError("Configure GitHub App credentials or GITHUB_TOKEN for automatic reviews")


def publish_commit_status(
    owner: str,
    repository: str,
    sha: str,
    state: str,
    description: str,
    token: str,
    target_url: str = "",
) -> None:
    response = httpx.post(
        f"{API}/repos/{owner}/{repository}/statuses/{sha}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Regora",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "state": state,
            "context": "Regora / PR Guardian",
            "description": description[:140],
            **({"target_url": target_url} if target_url else {}),
        },
        timeout=20,
    )
    if response.status_code != 201:
        raise RuntimeError("GitHub did not accept the Regora commit status")
