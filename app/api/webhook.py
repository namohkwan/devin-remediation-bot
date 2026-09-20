"""GitHub webhook endpoint (webhook trigger mode)."""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.config import Settings, get_settings
from app.core.orchestrator import Orchestrator, get_orchestrator
from app.services.reporting import serialize_run

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])

SIGNATURE_PREFIX = "sha256="


def verify_signature(payload: bytes, signature_header: str | None, secret: str) -> bool:
    """Validate the ``X-Hub-Signature-256`` header against ``payload``."""
    if not signature_header or not signature_header.startswith(SIGNATURE_PREFIX):
        return False
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(SIGNATURE_PREFIX + digest, signature_header)


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, object]:
    """Handle GitHub ``issues`` events and trigger remediation on the trigger label."""
    body = await request.body()
    if not verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
        logger.warning("Rejected webhook delivery with an invalid signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature"
        )

    if x_github_event == "ping":
        return {"status": "ignored", "reason": "ping event"}
    if x_github_event != "issues":
        return {"status": "ignored", "reason": f"unsupported event: {x_github_event}"}

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload"
        ) from exc

    action = payload.get("action")
    label_name = (payload.get("label") or {}).get("name")
    issue_number = (payload.get("issue") or {}).get("number")

    if action != "labeled" or label_name != settings.trigger_label:
        return {
            "status": "ignored",
            "reason": f"action={action} label={label_name}",
        }
    if not isinstance(issue_number, int):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing issue number"
        )

    run = orchestrator.run_for_issue(issue_number, trigger="webhook")
    return {"status": "accepted", "run": serialize_run(run)}
