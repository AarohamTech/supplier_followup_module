"""PO acknowledgement endpoints.

Public (no login) — the signed link in PO follow-up mails:
  GET  /api/po-ack/{token}   → PO + acknowledgement status (read-only)
  POST /api/po-ack/{token}   → record the acknowledgement (idempotent)

The company schema comes from the signed token, never from a session, so these
routes work for a supplier who has never logged in.

Supplier portal (logged-in supplier, own POs only):
  GET  /api/portal/po-ack/{supplier_po_no}
  POST /api/portal/po-ack/{supplier_po_no}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.deps import get_current_supplier
from ..core.tenant import use_company
from ..database import SessionLocal, get_db
from ..models.user import User
from ..services import po_ack_service

public_router = APIRouter(prefix="/api/po-ack", tags=["po-ack"])
portal_router = APIRouter(prefix="/api/portal/po-ack", tags=["po-ack"])


def _client_ip(request: Request) -> str | None:
    # Browser → Vercel rewrite → Cloudflare Tunnel → uvicorn: the first
    # X-Forwarded-For hop is the real client; CF-Connecting-IP is the proxy.
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else None


def _schema_or_404(token: str) -> str:
    try:
        return str(po_ack_service.verify_token(token)["s"])
    except po_ack_service.InvalidAckToken:
        raise HTTPException(404, "This acknowledgement link is not valid.")


@public_router.get("/{token}")
def public_status(token: str) -> dict[str, Any]:
    schema = _schema_or_404(token)
    with use_company(schema):
        db = SessionLocal()
        try:
            out = po_ack_service.status_by_token(db, token)
        finally:
            db.close()
    if not out["found"]:
        raise HTTPException(404, "This purchase order could not be found.")
    return out


@public_router.post("/{token}")
def public_acknowledge(token: str, request: Request) -> dict[str, Any]:
    schema = _schema_or_404(token)
    with use_company(schema):
        db = SessionLocal()
        try:
            out = po_ack_service.acknowledge_by_token(
                db, token,
                ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        finally:
            db.close()
    if not out["found"]:
        raise HTTPException(404, "This purchase order could not be found.")
    return out


def _owned_po(db: Session, user: User, supplier_po_no: str):
    # Reuse the portal's own ownership + visibility rules.
    from .portal import _po_is_owned, _supplier_name

    name = _supplier_name(db, user)
    rec = _po_is_owned(db, name, supplier_po_no)
    if rec is None:
        raise HTTPException(404, "PO not found for your account")
    return rec


@portal_router.get("/{supplier_po_no}")
def portal_status(
    supplier_po_no: str,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rec = _owned_po(db, user, supplier_po_no)
    _anchor, _records, ref = po_ack_service.resolve_po(
        db, supplier_name=rec.supplier_name or "", supplier_po_no=rec.supplier_po_no,
        po_ref=rec.po_short_ref, record_id=rec.id,
    )
    row = po_ack_service.find_ack(db, rec.supplier_name, rec.supplier_po_no, ref)
    return {"po_ref": ref or rec.supplier_po_no, **po_ack_service.ack_out(row)}


@portal_router.post("/{supplier_po_no}")
def portal_acknowledge(
    supplier_po_no: str,
    request: Request,
    user: User = Depends(get_current_supplier),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rec = _owned_po(db, user, supplier_po_no)
    row, created, info = po_ack_service.acknowledge(
        db,
        supplier_name=rec.supplier_name or "",
        supplier_po_no=rec.supplier_po_no,
        po_ref=rec.po_short_ref,
        record_id=rec.id,
        via="portal",
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        user_id=user.id,
    )
    if row is None:
        raise HTTPException(404, "PO not found for your account")
    return {"created": created, "po_ref": info["display_ref"], **po_ack_service.ack_out(row)}
