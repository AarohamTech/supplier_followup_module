"""Webhook router for invoking mail workers from external systems.

Machine-to-machine: every call must present the shared secret in the
`X-Webhook-Secret` header, matched against `settings.WEBHOOK_SECRET`. If no
secret is configured the endpoints fail closed (reject all calls).
"""
from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from ..core.config import settings
from ..workers import mail_fetch_worker, mail_send_worker

log = logging.getLogger(__name__)


def require_webhook_secret(x_webhook_secret: str | None = Header(default=None)) -> None:
    expected = settings.WEBHOOK_SECRET
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret not configured (set WEBHOOK_SECRET).",
        )
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook secret.",
        )


router = APIRouter(
    prefix="/api/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(require_webhook_secret)],
)


def _summarize_fetch_result(result: dict[str, Any]) -> dict[str, Any]:
    processed = result.get("processed") or []
    matched_supplier_count = sum(1 for row in processed if row.get("supplier_id") is not None)
    matched_procurement_count = sum(
        1 for row in processed if row.get("procurement_record_id") is not None
    )
    skipped_count = sum(1 for row in processed if row.get("skipped"))
    status_change_count = sum(1 for row in processed if row.get("status_change_applied"))

    return {
        "enabled": result.get("enabled", False),
        "protocol": result.get("protocol"),
        "fetched": result.get("fetched", 0),
        "processed_count": len(processed),
        "skipped_count": skipped_count,
        "matched_supplier_count": matched_supplier_count,
        "matched_procurement_count": matched_procurement_count,
        "status_change_applied_count": status_change_count,
        "error": result.get("error"),
        "sample": processed[:5],
    }


@router.post("/mail-fetch")
def trigger_mail_fetch(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    """Trigger the mailbox fetch worker. Safe when MAIL_INBOX_ENABLED=false."""
    return mail_fetch_worker.fetch_supplier_mails(limit=limit)


@router.post("/mail-fetch/test")
def test_mail_fetch(limit: int = Query(5, ge=1, le=50)) -> dict[str, Any]:
    """Run the mailbox fetch worker and return a compact testing summary."""
    result = mail_fetch_worker.fetch_supplier_mails(limit=limit)
    return _summarize_fetch_result(result)


@router.post("/mail-send")
def trigger_mail_send(limit: int = Query(25, ge=1, le=500)) -> dict[str, Any]:
    """Trigger the SMTP send worker for any READY outgoing messages.

    Safe when SMTP_ENABLED=false.
    """
    return mail_send_worker.send_ready_messages(limit=limit)


@router.post("/mail-send/test")
def test_mail_send() -> dict[str, Any]:
    """Validate SMTP connectivity and credentials without sending a message."""
    return mail_send_worker.test_smtp_connection()
