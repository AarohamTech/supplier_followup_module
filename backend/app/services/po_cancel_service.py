"""PO cancellation requests.

An employee raises a cancellation for one of their POs. We flip the PO's material
lines to ``cancellation_status = "PENDING"`` and POST a cancel request to the
CRM/ERP (:func:`_raise_external_cancel`, contract in docs/PO_CANCEL_ERP_API.md).
The PO stays "Pending cancellation" until the ERP calls back
``POST /api/webhooks/po-cancel-confirm``, which runs :func:`confirm_cancellation`
(CANCELLED) or :func:`reject_cancellation`.

The request body carries the documented header fields plus, per line, EVERY field
the CRM desk feed originally gave us (``ProcurementRecord.crm_raw``), so the ERP
can match the line on whatever key it prefers. Rows ingested before ``crm_raw``
existed get the same keys reconstructed from their mapped columns.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
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

    # The ERP request carries the PO header plus, per line, the customer context
    # and every original CRM feed field (build_cancel_payload).
    external = _raise_external_cancel(
        db,
        rows,
        supplier_po_no=supplier_po_no,
        supplier_name=supplier_name or rows[0].supplier_name,
        requested_by=requested_by,
        remark=remark,
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


def request_line_cancellation(
    db: Session,
    *,
    record_id: int,
    requested_by: str | None,
    remark: str | None = None,
) -> dict[str, Any] | None:
    """Material-wise cancel: mark ONE PO line pending-cancellation and raise the
    external request for just that line. Returns None if the record is unknown."""
    rec = db.get(ProcurementRecord, record_id)
    if rec is None:
        return None
    remark = (remark or "").strip()[:500] or None
    if (rec.cancellation_status or "").upper() not in _TERMINAL:
        rec.cancellation_status = PENDING
        rec.cancel_requested_by = requested_by
        rec.cancel_requested_at = datetime.utcnow()
        rec.cancel_remark = remark
        db.commit()

    external = _raise_external_cancel(
        db,
        [rec],
        supplier_po_no=rec.supplier_po_no,
        supplier_name=rec.supplier_name,
        requested_by=requested_by,
        remark=remark,
    )
    return {
        "procurement_record_id": rec.id,
        "supplier_po_no": rec.supplier_po_no,
        "material_name": rec.material_name,
        "cancellation_status": PENDING,
        "external": external,
    }


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


def _iso(v: Any) -> str | None:
    if v in (None, ""):
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def crm_fields_for(rec: ProcurementRecord) -> dict[str, Any]:
    """Every CRM feed field for a PO line: the stored raw desk row when we have it,
    else the same keys rebuilt from the mapped columns (rows ingested before
    ``crm_raw`` existed). Keys follow the CRM's own names (GetPendingUserDesk)."""
    raw = getattr(rec, "crm_raw", None)
    if isinstance(raw, dict) and raw:
        return dict(raw)
    return {
        "CRMNo": rec.crm_no,
        "PoNo": rec.supplier_po_no,
        "PoShortRefTrnNo": rec.po_short_ref,
        "PoRefTrnNo": rec.po_trn_no,
        "PoRefTrnDate": _iso(rec.supplier_date),
        "PoLongName": rec.supplier_name,
        "PoStatus": rec.po_status,
        "AdvanceStatus": rec.adv_status,
        "PoType": rec.po_type,
        "MaterialName": rec.material_name,
        "MaterialUom": rec.uom,
        "Quantity": _num(rec.qty),
        "PoQuantity": _num(rec.quantity),
        "PoQty": _num(rec.po_qty),
        "GrnQty": _num(rec.grn_qty),
        "PendQty": _num(rec.pending_qty),
        "Rate": _num(rec.rate),
        "Stock": _num(rec.stock),
        "Signal": rec.signal,
        "ShipmentDate": _iso(rec.shipment_date),
        "LeadTime": rec.lead_time,
        "UserId": rec.owner_emp_code,
        "LongName": rec.customer_name,
        "RefTrnNo": rec.po_no if rec.po_no != rec.supplier_po_no else None,
        "RefTrnDate": _iso(rec.po_date),
        "Remark": rec.po_remark,
    }


def build_cancel_payload(
    rows: list[ProcurementRecord],
    *,
    company_id: str | None,
    supplier_po_no: str,
    supplier_name: str | None,
    requested_by: str | None,
    remark: str | None,
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    """The ERP cancel request body (docs/PO_CANCEL_ERP_API.md). Header fields
    identify the PO; each line carries the documented summary fields plus
    ``CrmFields`` — the complete original CRM record for that line."""
    first = rows[0]
    ref = next((r.po_short_ref for r in rows if r.po_short_ref), None)
    trn = next((r.po_trn_no for r in rows if r.po_trn_no), None)
    at = (requested_at or datetime.utcnow()).replace(microsecond=0)
    return {
        "CompanyId": company_id,
        "PoNo": supplier_po_no,
        "PoShortRefTrnNo": ref,
        "PoRefTrnNo": trn,
        "SupplierName": supplier_name,
        "PoDate": _iso(first.supplier_date),
        "RequestedBy": requested_by,
        "Remark": remark,
        "RequestedAt": at.isoformat() + "Z",
        "Lines": [
            {
                "ProcurementRecordId": r.id,
                "CrmNo": r.crm_no,
                "MaterialName": r.material_name,
                "Qty": _num(r.qty),
                "CustomerName": r.customer_name,
                "CustomerPoNo": r.po_no if r.po_no != r.supplier_po_no else None,
                "CustomerPoDate": _iso(r.po_date),
                "CancelRemark": r.cancel_remark,
                "CrmFields": crm_fields_for(r),
            }
            for r in rows
        ],
    }


def _raise_external_cancel(
    db: Session,
    rows: list[ProcurementRecord],
    *,
    supplier_po_no: str,
    supplier_name: str | None,
    requested_by: str | None,
    remark: str | None,
) -> dict[str, Any]:
    """POST the cancel request to the CRM/ERP for the current company.

    Best-effort and never raises: the PO is already marked pending locally, so a
    failed or unconfigured call just reports ``raised: False`` with the reason.
    The bearer token is the desk-feed login; a 401 triggers one forced refresh.
    """
    if not rows:
        return {"raised": False, "reason": "no PO lines"}
    if not getattr(settings, "CRM_CANCEL_API_ENABLED", True):
        return {"raised": False, "reason": "CRM_CANCEL_API_ENABLED is false"}

    from .crm_config import get_current_crm_config

    try:
        cfg = get_current_crm_config(db)
    except Exception as exc:  # noqa: BLE001
        log.exception("PO cancel: could not resolve CRM config")
        return {"raised": False, "reason": f"CRM config error: {exc}"}
    if cfg is None:
        return {"raised": False, "reason": "CRM connection is not configured"}

    payload = build_cancel_payload(
        rows,
        company_id=cfg.desk_id,
        supplier_po_no=supplier_po_no,
        supplier_name=supplier_name,
        requested_by=requested_by,
        remark=remark,
    )
    path = (getattr(settings, "CRM_CANCEL_API_PATH", "") or "/api/crm/PoCancelRequest").strip()
    url = f"{cfg.base_url.rstrip('/')}/{path.lstrip('/')}"

    import requests

    from . import crm_ingest_service

    def _post(token: str) -> "requests.Response":
        return requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=settings.CRM_HTTP_TIMEOUT_SECONDS,
        )

    try:
        resp = _post(crm_ingest_service.get_token(cfg))
        if resp.status_code == 401:
            resp = _post(crm_ingest_service.get_token(cfg, force_refresh=True))
        try:
            body: Any = resp.json()
        except ValueError:
            body = (resp.text or "")[:500]
        ok = 200 <= resp.status_code < 300
        (log.info if ok else log.warning)(
            "PO cancel request %s -> HTTP %s (po=%s supplier=%s lines=%d)",
            url, resp.status_code, supplier_po_no, supplier_name, len(rows),
        )
        out: dict[str, Any] = {
            "raised": ok,
            "url": url,
            "status_code": resp.status_code,
            "response": body,
            "lines": len(rows),
        }
        if not ok:
            out["reason"] = f"ERP returned HTTP {resp.status_code}"
        return out
    except Exception as exc:  # noqa: BLE001
        log.exception("PO cancel request to %s failed", url)
        return {"raised": False, "url": url, "reason": str(exc)[:300], "lines": len(rows)}
