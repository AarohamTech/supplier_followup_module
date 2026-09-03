"""Mail Log — every outgoing message (auto follow-ups, acknowledgements,
credentials, staff compose, replies) with who it went to and what happened.

Read-only. Answers "did the supplier get mailed, when, and if not why not":
status (SENT / READY / FAILED / DRAFT), recipients, mail type, error text, and,
for READY auto follow-ups outside the send window, the local time it will go.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from ..core.deps import require_role
from ..core.roles import Role
from ..database import get_db
from ..models.communication_message import CommunicationMessage as M
from ..services import settings_service
from ..workers.mail_send_worker import is_held_mail_type

router = APIRouter(
    prefix="/api/mail-log",
    tags=["mail-log"],
    dependencies=[Depends(require_role(Role.VIEWER))],
)

STATUSES = ("SENT", "READY", "FAILED", "DRAFT")


def _filters(
    *,
    status: str | None,
    mail_type: str | None,
    search: str | None,
    date_from: date | None,
    date_to: date | None,
) -> list[Any]:
    conds: list[Any] = [M.direction == "OUTGOING"]
    if status:
        conds.append(func.upper(M.status) == status.strip().upper())
    if mail_type:
        conds.append(func.upper(M.mail_type) == mail_type.strip().upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        conds.append(or_(
            M.supplier_name.ilike(like),
            M.receiver_email.ilike(like),
            M.subject.ilike(like),
            M.supplier_po_no.ilike(like),
            # to_emails is a JSON list; a text cast makes it searchable on both
            # SQLite (tests) and Postgres.
            cast(M.to_emails, String).ilike(like),
        ))
    if date_from:
        conds.append(M.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        conds.append(
            M.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time())
        )
    return conds


def _item(m: M, *, window_open: bool, next_change: str) -> dict[str, Any]:
    status = (m.status or "").upper()
    held = status == "READY" and not window_open and is_held_mail_type(m.mail_type)
    return {
        "id": m.id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "sent_at": m.sent_at.isoformat() if m.sent_at else None,
        "supplier_id": m.supplier_id,
        "supplier_name": m.supplier_name,
        "supplier_po_no": m.supplier_po_no,
        "to_emails": list(m.to_emails or []),
        "cc_emails": list(m.cc_emails or []),
        "receiver_email": m.receiver_email,
        "mail_type": m.mail_type,
        "subject": m.subject,
        "status": status or None,
        "error_message": m.error_message,
        "held": held,
        "held_until": next_change if held else None,
    }


def _window_state(db: Session) -> tuple[dict[str, Any], bool, str]:
    window = settings_service.get_mail_send_window(db)
    now = datetime.utcnow()
    return (
        window,
        settings_service.window_is_open(window, now),
        settings_service.next_window_change(window, now),
    )


@router.get("")
def list_mail_log(
    status: str | None = Query(default=None, description="SENT / READY / FAILED / DRAFT"),
    mail_type: str | None = Query(default=None),
    search: str | None = Query(default=None, description="supplier, recipient, subject or PO"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    conds = _filters(status=status, mail_type=mail_type, search=search,
                     date_from=date_from, date_to=date_to)
    total = db.scalar(select(func.count()).select_from(M).where(*conds)) or 0
    rows = db.scalars(
        select(M).where(*conds).order_by(M.created_at.desc(), M.id.desc())
        .limit(size).offset((page - 1) * size)
    ).all()

    # Status tiles ignore the status filter (so they stay stable while you click
    # through them) but honour every other filter.
    tile_conds = _filters(status=None, mail_type=mail_type, search=search,
                          date_from=date_from, date_to=date_to)
    counts: dict[str, int] = {s: 0 for s in STATUSES}
    for st, n in db.execute(
        select(func.upper(M.status), func.count()).where(*tile_conds).group_by(func.upper(M.status))
    ).all():
        counts[st or "UNKNOWN"] = int(n or 0)

    window, window_open, next_change = _window_state(db)
    mail_types = [
        t for (t,) in db.execute(
            select(M.mail_type).where(M.direction == "OUTGOING", M.mail_type.isnot(None))
            .group_by(M.mail_type).order_by(M.mail_type)
        ).all()
    ]
    return {
        "items": [_item(m, window_open=window_open, next_change=next_change) for m in rows],
        "total": int(total),
        "page": page,
        "size": size,
        "counts": counts,
        "mail_types": mail_types,
        "window": {
            "enabled": bool(window.get("enabled", True)),
            "open": window_open,
            "next_change": next_change,
            "timezone": window.get("timezone"),
        },
    }


@router.get("/export")
def export_mail_log(
    status: str | None = Query(default=None),
    mail_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    conds = _filters(status=status, mail_type=mail_type, search=search,
                     date_from=date_from, date_to=date_to)
    rows = db.scalars(
        select(M).where(*conds).order_by(M.created_at.desc(), M.id.desc()).limit(5000)
    ).all()
    _, window_open, next_change = _window_state(db)

    wb = Workbook()
    ws = wb.active
    ws.title = "Mail log"
    ws.append(["Queued at", "Sent at", "Status", "Held until", "Supplier", "PO", "To", "Cc",
               "Mail type", "Subject", "Error"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for m in rows:
        it = _item(m, window_open=window_open, next_change=next_change)
        ws.append([
            it["created_at"], it["sent_at"], it["status"], it["held_until"],
            it["supplier_name"], it["supplier_po_no"],
            ", ".join(it["to_emails"]) or (it["receiver_email"] or ""),
            ", ".join(it["cc_emails"]), it["mail_type"], it["subject"], it["error_message"],
        ])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=mail_log.xlsx"},
    )
