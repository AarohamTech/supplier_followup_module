"""PO cancellation requests.

An employee raises a cancellation for one of their POs. We flip the PO's material
lines to ``cancellation_status = "PENDING"`` and call the external CRM cancel API.
The PO stays "Pending cancellation" until that API confirms, at which point
:func:`confirm_cancellation` flips it to ``"CANCELLED"``.

NOTE: the external CRM cancel API format is not finalized yet, so
``_raise_external_cancel`` is a placeholder that records the intent (PO shows as
pending) without calling anything. Wire the real request there when the format is
provided; a confirmation step (webhook/cron) then calls ``confirm_cancellation``.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.procurement import ProcurementRecord

log = logging.getLogger(__name__)

PENDING = "PENDING"
CANCELLED = "CANCELLED"
_TERMINAL = {CANCELLED}


def _records_for_po(
    db: Session, supplier_po_no: str, supplier_name: str | None, owner_emp_code: str | None
) -> list[ProcurementRecord]:
    stmt = select(ProcurementRecord).where(ProcurementRecord.supplier_po_no == supplier_po_no)
    # PO numbers are recycled across suppliers, so scope to the supplier when known.
    if supplier_name:
        stmt = stmt.where(
            func.upper(ProcurementRecord.supplier_name) == supplier_name.strip().upper()
        )
    # Employee callers pass their emp_code so they can only touch their own POs.
    if owner_emp_code:
        stmt = stmt.where(ProcurementRecord.owner_emp_code == owner_emp_code)
    return list(db.scalars(stmt).all())


def request_cancellation(
    db: Session,
    *,
    supplier_po_no: str,
    supplier_name: str | None,
    requested_by: str | None,
    owner_emp_code: str | None = None,
    remark: str | None = None,
) -> dict[str, Any] | None:
    """Mark a PO's lines as pending-cancellation and raise the external request.

    Returns a summary dict, or None if no matching (owned) PO was found. Idempotent:
    re-requesting an already-pending PO simply keeps it pending.
    """
    rows = _records_for_po(db, supplier_po_no, supplier_name, owner_emp_code)
    if not rows:
        return None

    remark = (remark or "").strip()[:500] or None
    now = datetime.utcnow()
    for r in rows:
        if (r.cancellation_status or "").upper() not in _TERMINAL:
            r.cancellation_status = PENDING
            r.cancel_requested_by = requested_by
            r.cancel_requested_at = now
            r.cancel_remark = remark
    db.commit()

    # The PO chain starts from a customer order, so the ERP request carries the
    # customer context per line (name, order ref/date) plus the supplier PO date.
    lines = [
        {
            "CrmNo": r.crm_no,
            "MaterialName": r.material_name,
            "Qty": float(r.qty) if r.qty is not None else None,
            "CustomerName": r.customer_name,
            "CustomerPoNo": r.po_no if r.po_no != r.supplier_po_no else None,
            "CustomerPoDate": r.po_date.isoformat() if r.po_date else None,
        }
        for r in rows
    ]
    external = _raise_external_cancel(
        supplier_po_no=supplier_po_no,
        supplier_name=supplier_name,
        po_date=rows[0].supplier_date.isoformat() if rows[0].supplier_date else None,
        requested_by=requested_by,
        remark=remark,
        lines=lines,
    )
    return {
        "supplier_po_no": supplier_po_no,
        "supplier_name": supplier_name,
        "cancellation_status": PENDING,
        "records_updated": len(rows),
        "external": external,
    }


def confirm_cancellation(
    db: Session, *, supplier_po_no: str, supplier_name: str | None = None
) -> int:
    """Flip a pending PO to CANCELLED once the external API confirms. Returns the
    number of records updated. Not triggered yet — wired when the CRM callback exists."""
    rows = _records_for_po(db, supplier_po_no, supplier_name, owner_emp_code=None)
    updated = 0
    for r in rows:
        if (r.cancellation_status or "").upper() == PENDING:
            r.cancellation_status = CANCELLED
            updated += 1
    if updated:
        db.commit()
    return updated


def reject_cancellation(
    db: Session, *, supplier_po_no: str, supplier_name: str | None = None
) -> int:
    """ERP declined the cancel: clear the pending flag so the PO returns to its
    normal lifecycle. Returns the number of records updated."""
    rows = _records_for_po(db, supplier_po_no, supplier_name, owner_emp_code=None)
    updated = 0
    for r in rows:
        if (r.cancellation_status or "").upper() == PENDING:
            r.cancellation_status = None
            r.cancel_requested_by = None
            r.cancel_requested_at = None
            r.cancel_remark = None
            updated += 1
    if updated:
        db.commit()
    return updated


def _raise_external_cancel(**kwargs: Any) -> dict[str, Any]:
    """Placeholder for the external CRM PO-cancel API call.

    The API format will be provided later. When wired, POST the cancel request to
    the CRM here and return its response. For now this is a no-op so the PO shows as
    'Pending cancellation' without any outbound call.
    """
    log.info("PO cancel requested (external cancel API not configured yet): %s", kwargs)
    return {"raised": False, "reason": "external cancel API not configured"}
