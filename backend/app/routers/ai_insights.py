"""AI insights router — predictive delivery risk + supplier scorecards.

Mounted separately from the chat router so analytics endpoints stay grouped:

  GET  /api/ai/insights/delay-risk              → top at-risk POs
  POST /api/ai/insights/delay-risk/rescore      → recompute risk now (manager)
  GET  /api/ai/insights/suppliers               → supplier scorecards (worst first)
  GET  /api/ai/insights/suppliers/{name}        → one supplier's scorecard
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import roles as roles_mod
from ..core.deps import get_current_user, require_manager
from ..core.roles import Role
from ..database import get_db
from ..models.mail_history import MailHistory
from ..services import ai_insights_service, followup_audit_service, po_followup_mail_service

router = APIRouter(prefix="/api/ai/insights", tags=["ai-insights"])


@router.get("/delay-risk")
def delay_risk(
    db: Session = Depends(get_db),
    band: str | None = Query(default=None, description="Filter: LOW / MEDIUM / HIGH"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    items = ai_insights_service.list_delay_risk(db, band=band, limit=limit)
    return {
        "count": len(items),
        "band": band,
        "items": items,
    }


@router.post("/delay-risk/rescore")
def rescore_delay_risk(
    db: Session = Depends(get_db),
    _user=Depends(require_manager),
) -> dict:
    return ai_insights_service.rescore_all(db)


@router.get("/black-followups")
def black_followups(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=300),
) -> dict:
    """BLACK-signal POs with their AI conversation thread + commitment status."""
    items = ai_insights_service.list_black_followups(db, limit=limit)
    return {
        "count": len(items),
        "chasing": sum(1 for i in items if not i["commitment_captured"]),
        "items": items,
    }


@router.get("/followup-history")
def followup_history(
    db: Session = Depends(get_db),
    signal: str | None = Query(default=None, description="Filter by signal e.g. BLACK"),
    outcome: str | None = Query(default=None, description="QUEUED / SKIPPED / FAILED"),
    supplier_po_no: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
) -> dict:
    """Audit log of follow-up attempts (auto + manual) — every attempt, even the
    ones that were skipped or failed, with AI status and the linked send result."""
    rows = followup_audit_service.list_attempts(
        db, signal=signal, outcome=outcome, supplier_po_no=supplier_po_no, limit=limit
    )
    # Batch the linked mail send status so the UI can show Sent/Failed/Queued.
    hist_ids = [r.history_id for r in rows if r.history_id]
    sent_by_hist: dict[int, MailHistory] = {}
    if hist_ids:
        for h in db.scalars(select(MailHistory).where(MailHistory.id.in_(hist_ids))).all():
            sent_by_hist[h.id] = h

    items = []
    for r in rows:
        h = sent_by_hist.get(r.history_id) if r.history_id else None
        items.append({
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "supplier_po_no": r.supplier_po_no,
            "supplier_name": r.supplier_name,
            "signal": r.signal,
            "mail_type": r.mail_type,
            "source": r.source,
            "outcome": r.outcome,
            "detail": r.detail,
            "ai_used": r.ai_used,
            "ai_error": r.ai_error,
            "history_id": r.history_id,
            "send_status": h.sent_status if h else None,
            "sent_at": h.sent_at.isoformat() if (h and h.sent_at) else None,
            "send_error": h.remarks if h else None,
        })
    return {"count": len(items), "items": items}


class FollowupCommand(BaseModel):
    supplier_po_no: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=2000)
    send: bool = False


@router.post("/black-followups/command")
def black_followup_command(
    payload: FollowupCommand,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """Tell the AI what to follow up on for a PO. Preview (default, user+) or
    actually send it to the supplier (send=true, manager+)."""
    if not roles_mod.role_at_least(user.role, Role.USER):
        raise HTTPException(403, "Read-only role — commanding the AI requires 'user' or higher")
    if payload.send and not roles_mod.role_at_least(user.role, Role.MANAGER):
        raise HTTPException(403, "Sending a follow-up requires 'manager' or higher")
    result = po_followup_mail_service.command_followup(
        db,
        supplier_po_no=payload.supplier_po_no,
        instruction=payload.instruction,
        send=payload.send,
    )
    if not result.get("found"):
        raise HTTPException(404, result.get("error") or "PO not found")
    return result


@router.get("/suppliers")
def supplier_scorecards(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    items = ai_insights_service.supplier_scorecards(db, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/suppliers/{name}")
def supplier_scorecard(name: str, db: Session = Depends(get_db)) -> dict:
    items = ai_insights_service.supplier_scorecards(db, name=name, limit=1)
    if not items:
        raise HTTPException(404, f"No procurement records for supplier '{name}'")
    return items[0]
