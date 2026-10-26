"""Signed GitHub webhook intake for automatic pull-request reviews."""

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from rq import Queue

from app.graph.store import GraphStore, get_store
from app.services.cache import redis_connection
from app.services.github_app import verify_webhook_signature
from app.services.pr_guardian import guardian_job_failure, review_pull_request
from app.services.pull_requests import parse_pull_request_url

router = APIRouter(prefix="/api/github")
PR_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
COMMAND = re.compile(r"^/regora\s+(review|impact|explain)\s*$", re.IGNORECASE)


def selected_pull_request(event: str, payload: dict) -> tuple[str, str] | None:
    if event == "pull_request":
        pull_request = payload.get("pull_request") or {}
        if payload.get("action") not in PR_ACTIONS or pull_request.get("draft"):
            return None
        return pull_request.get("html_url", ""), "review"
    if event == "issue_comment":
        issue = payload.get("issue") or {}
        comment = payload.get("comment") or {}
        match = COMMAND.fullmatch((comment.get("body") or "").strip())
        if (
            payload.get("action") != "created"
            or not issue.get("pull_request")
            or comment.get("author_association") not in TRUSTED_ASSOCIATIONS
            or not match
        ):
            return None
        return issue["pull_request"].get("html_url", ""), match.group(1).lower()
    return None


@router.post("/webhooks", status_code=202)
async def github_webhook(
    request: Request,
    store: GraphStore = Depends(get_store),
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
):
    length = request.headers.get("content-length", "0")
    if not length.isdigit() or int(length) > 1_000_000:
        raise HTTPException(413, "GitHub webhook payload is too large")
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(413, "GitHub webhook payload is too large")
    try:
        verify_webhook_signature(body, x_hub_signature_256)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc
    if not x_github_delivery or len(x_github_delivery) > 100:
        raise HTTPException(422, "Missing GitHub delivery identifier")
    delivery_key = f"regora:github-delivery:{x_github_delivery}"
    if not redis_connection().set(delivery_key, "1", nx=True, ex=86400):
        return {"status": "duplicate", "delivery_id": x_github_delivery}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        redis_connection().delete(delivery_key)
        raise HTTPException(400, "Invalid GitHub webhook JSON") from exc
    if x_github_event == "ping":
        return {"status": "pong", "delivery_id": x_github_delivery}
    selected = selected_pull_request(x_github_event, payload)
    if not selected:
        return {"status": "ignored", "delivery_id": x_github_delivery}
    pr_url, command = selected
    full_name = (payload.get("repository") or {}).get("full_name", "")
    installation_id = (payload.get("installation") or {}).get("id")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name) or not isinstance(installation_id, int):
        raise HTTPException(422, "GitHub webhook is missing repository installation data")
    owner, name = full_name.split("/", 1)
    try:
        pr_owner, pr_name, _ = parse_pull_request_url(pr_url)
    except ValueError as exc:
        raise HTTPException(422, "GitHub webhook contains an invalid pull request URL") from exc
    if (pr_owner.lower(), pr_name.lower()) != (owner.lower(), name.lower()):
        raise HTTPException(422, "Pull request does not belong to the webhook repository")
    try:
        binding = store.github_repository(owner, name, installation_id)
    except Exception:
        redis_connection().delete(delivery_key)
        raise
    if binding["status"] != "BOUND":
        reason = {
            "NOT_FOUND": "repository_not_indexed",
            "AMBIGUOUS": "ambiguous_repository_binding",
            "CONFLICT": "repository_binding_conflict",
        }.get(binding["status"], "repository_binding_failed")
        # GitHub redelivery reuses the delivery id. Let owners correct an
        # indexing or binding problem and redeliver this exact event.
        redis_connection().delete(delivery_key)
        return {
            "status": "ignored",
            "reason": reason,
            "delivery_id": x_github_delivery,
        }
    repository = binding["repository"]
    created_at = datetime.now(UTC).isoformat()
    head_sha = ((payload.get("pull_request") or {}).get("head") or {}).get("sha", "")
    pull_request_number = ((payload.get("pull_request") or payload.get("issue") or {}).get("number") or 0)
    run = None
    try:
        run = store.create_guardian_run(
            {
                "id": str(uuid4()),
                "repository_id": repository["id"],
                "status": "QUEUED",
                "pull_request": pull_request_number,
                "pr_url": pr_url,
                "head_sha": head_sha,
                "command": command,
                "installation_id": installation_id,
                "delivery_id": x_github_delivery,
                "retry_of": "",
                "created_at": created_at,
                "updated_at": created_at,
                "error": "",
            }
        )
        job = Queue("pull-requests", connection=redis_connection()).enqueue(
            review_pull_request,
            repository["id"],
            pr_url,
            installation_id,
            x_github_delivery,
            command,
            head_sha,
            run["id"],
            job_timeout=600,
            result_ttl=86400,
            failure_ttl=604800,
            on_failure=guardian_job_failure,
        )
    except Exception:
        redis_connection().delete(delivery_key)
        if run:
            store.update_guardian_run(
                run["id"],
                status="ERROR",
                error="Could not queue the automatic review",
                updated_at=datetime.now(UTC).isoformat(),
            )
        raise
    return {
        "status": "queued",
        "command": command,
        "repository_id": repository["id"],
        "job_id": job.id,
        "run_id": run["id"],
        "delivery_id": x_github_delivery,
    }
