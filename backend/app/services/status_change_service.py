"""Reconcile parsed supplier replies against procurement_records.

When a parsed reply contains new status / shipment date / quantity values that
differ from what is on the linked procurement_records row, the row is updated
and a status_change_log entry is recorded.

This module never derives the signal — that is left to the upstream Excel/ERP
intake exactly as today. It only mirrors supplier-confirmed facts back.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.procurement import ProcurementRecord
from ..models.status_change_log import StatusChangeLog
from . import po_followup_service
from .reply_table_parser import parse_reply_table

log = logging.getLogger(__name__)

# Supplier-reply status string → procurement_records.po_status (best effort).
_STATUS_MAP: dict[str, str] = {
    "confirmed": "CONFIRMED",
    "dispatched": "DISPATCHED",
    "shipped": "DISPATCHED",
    "ready": "READY",
    "in production": "IN_PRODUCTION",
    "delayed": "DELAYED",
    "hold": "ON_HOLD",
    "on hold": "ON_HOLD",
    "cancelled": "CANCELLED",
    "partial": "PARTIAL",
}


def _norm_status(raw: str | None) -> str | None:
    if not raw:
        return None
    return _STATUS_MAP.get(raw.strip().lower())


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def _norm_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _match_material_records(
    db: Session,
    *,
    message: CommunicationMessage,
    material_code: str | None,
    material_name: str | None,
    quantity: float | None,
) -> list[ProcurementRecord]:
    if not message.supplier_po_no:
        return []

    stmt = select(ProcurementRecord).where(
        ProcurementRecord.supplier_po_no == message.supplier_po_no.strip()
    )
    candidates = list(db.scalars(stmt).all())
    if not candidates:
        return []

    if message.supplier_name:
        supplier_matches = [
            r
            for r in candidates
            if _norm_text(r.supplier_name) == _norm_text(message.supplier_name)
        ]
        if supplier_matches:
            candidates = supplier_matches

    code_key = _norm_text(material_code)
    name_key = _norm_text(material_name)
    if code_key:
        code_matches = [r for r in candidates if _norm_text(r.crm_no) == code_key]
        if code_matches:
            candidates = code_matches

    if name_key:
        name_matches = [r for r in candidates if _norm_text(r.material_name) == name_key]
        if name_matches:
            candidates = name_matches

    if quantity is not None:
        qty_matches = [
            r
            for r in candidates
            if r.qty is not None and abs(float(r.qty) - float(quantity)) <= 1e-9
        ]
        if qty_matches:
            candidates = qty_matches
        else:
            supplier_qty_matches = [
                r
                for r in candidates
                if r.quantity is not None and abs(float(r.quantity) - float(quantity)) <= 1e-9
            ]
            if supplier_qty_matches:
                candidates = supplier_qty_matches

    return candidates


def _mirror_commitment_to_record(
    rec: ProcurementRecord,
    *,
    quantity: float | None,
    commitment_date_value: date | None,
    supplier_status: str | None,
    supplier_remark: str | None,
) -> None:
    if quantity is not None:
        rec.quantity = float(quantity)
    if commitment_date_value is not None:
        rec.commitment_date = commitment_date_value
    if supplier_status:
        rec.po_status = supplier_status
    if supplier_remark:
        rec.last_supplier_reply = supplier_remark[:1000]
        if supplier_status in {"DELAYED", "ON_HOLD", "CANCELLED"}:
            rec.delay_reason = supplier_remark[:500]


def apply_parsed_reply(
    db: Session,
    rec: ProcurementRecord,
    message: CommunicationMessage,
    parsed: dict[str, Any],
    *,
    commit: bool = True,
) -> StatusChangeLog | None:
    """Apply parsed fields to a procurement record. Returns the log entry if changes were made."""
    changes: list[str] = []

    old_status = rec.po_status
    old_shipment = _to_date(rec.shipment_date)
    old_qty = float(rec.qty) if rec.qty is not None else None

    new_status_raw = parsed.get("status")
    new_status = _norm_status(new_status_raw)
    if new_status and new_status != (rec.po_status or "").upper():
        rec.po_status = new_status
        changes.append(f"po_status:{old_status or '-'}→{new_status}")

    new_dt: datetime | None = parsed.get("_expected_dispatch_date_dt")
    if isinstance(new_dt, datetime):
        new_ship = new_dt.date()
        if new_ship and new_ship != old_shipment:
            rec.shipment_date = new_dt
            changes.append(
                f"shipment_date:{old_shipment.isoformat() if old_shipment else '-'}→{new_ship.isoformat()}"
            )

    new_qty = parsed.get("quantity")
    if isinstance(new_qty, (int, float)) and new_qty > 0 and (
        old_qty is None or abs((new_qty or 0) - (old_qty or 0)) > 1e-9
    ):
        rec.qty = float(new_qty)
        changes.append(f"qty:{old_qty if old_qty is not None else '-'}→{new_qty}")

    if parsed.get("remarks"):
        rec.last_supplier_reply = str(parsed["remarks"])[:1000]

    if not changes:
        if commit:
            db.commit()
        return None

    log_entry = StatusChangeLog(
        procurement_record_id=rec.id,
        source_message_id=message.id if message else None,
        old_status=old_status,
        new_status=rec.po_status,
        old_shipment_date=old_shipment,
        new_shipment_date=_to_date(rec.shipment_date),
        old_qty=old_qty,
        new_qty=float(rec.qty) if rec.qty is not None else None,
        action_taken="PARSED_REPLY_APPLIED",
        notes="; ".join(changes),
    )
    db.add(log_entry)
    if commit:
        db.commit()
        db.refresh(log_entry)
    return log_entry


def apply_material_reply_table(
    db: Session,
    message: CommunicationMessage,
    *,
    body: str | None,
    commit: bool = True,
) -> list[int]:
    """Parse a supplier reply for material-wise rows and upsert commitments.

    Returns the list of upserted commitment ids.
    """
    # Commitments are now captured via the portal commitment form, not by parsing
    # supplier email replies. The legacy parse-from-reply path is disabled unless
    # explicitly re-enabled via COMMITMENT_VIA_EMAIL_ENABLED.
    from ..core.config import settings as _settings

    if not getattr(_settings, "COMMITMENT_VIA_EMAIL_ENABLED", False):
        return []
    if not message or not message.supplier_po_no:
        return []
    text = body if body is not None else (message.body or "")
    rows = parse_reply_table(text)
    if not rows:
        return []

    ids: list[int] = []
    for row in rows:
        material_name = (row.get("material_name") or row.get("material_code") or "").strip()
        if not material_name:
            continue
        quantity = row.get("quantity")
        commitment_date_value = row.get("commitment_date")
        supplier_status = row.get("supplier_status")
        supplier_remark = row.get("remark")
        commitment = po_followup_service.upsert_commitment(
            db,
            supplier_po_no=message.supplier_po_no,
            material_name=material_name,
            procurement_record_id=message.procurement_record_id,
            supplier_id=message.supplier_id,
            supplier_name=message.supplier_name,
            material_code=row.get("material_code"),
            commitment_qty=quantity,
            commitment_date_value=commitment_date_value,
            supplier_status=supplier_status,
            supplier_remark=supplier_remark,
            reply_mail_id=message.id,
            commit=False,
        )
        ids.append(commitment.id)

        for rec in _match_material_records(
            db,
            message=message,
            material_code=row.get("material_code"),
            material_name=row.get("material_name"),
            quantity=quantity,
        ):
            _mirror_commitment_to_record(
                rec,
                quantity=quantity,
                commitment_date_value=commitment_date_value,
                supplier_status=supplier_status,
                supplier_remark=supplier_remark,
            )

    if commit:
        db.commit()
    return ids
