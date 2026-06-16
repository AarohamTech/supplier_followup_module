"""PO-wise follow-up grouping service.

Aggregates `procurement_records` by (supplier_name, supplier_po_no), computes
the highest-risk signal for the group, attaches the latest supplier-side
material commitments, and provides duplicate-draft detection for PO-wise mail
generation.

This module never mutates procurement signals — it only reads existing data
and exposes it in a PO-grouped shape.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models.mail_history import MailHistory
from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..models.supplier_email import SupplierEmail
from ..models.supplier_material_commitment import SupplierMaterialCommitment


SIGNAL_RANK: dict[str, int] = {"GREEN": 1, "YELLOW": 2, "RED": 3, "BLACK": 4}
_HEADER_LIKE_VALUES = {
    "CRM",
    "CRM NO",
    "MATERIAL",
    "MATERIAL NAME",
    "QTY",
    "QUANTITY",
    "STATUS",
    "REMARK",
    "REMARKS",
    "COMMITMENT DATE",
}


def _norm_signal(value: Optional[str]) -> str:
    v = (value or "GREEN").upper()
    return v if v in SIGNAL_RANK else "GREEN"


def highest_signal(signals: Iterable[Optional[str]]) -> str:
    """BLACK > RED > YELLOW > GREEN."""
    best = "GREEN"
    best_rank = SIGNAL_RANK[best]
    for sig in signals:
        norm = _norm_signal(sig)
        rank = SIGNAL_RANK[norm]
        if rank > best_rank:
            best, best_rank = norm, rank
    return best


def _group_key(record: ProcurementRecord) -> tuple[str, str]:
    return (
        (record.supplier_name or "").strip().upper(),
        (record.supplier_po_no or "").strip(),
    )


def _serialize_commitment(c: SupplierMaterialCommitment) -> dict[str, Any]:
    return {
        "id": c.id,
        "material_code": c.material_code,
        "material_name": c.material_name,
        "commitment_qty": float(c.commitment_qty) if c.commitment_qty is not None else None,
        "commitment_date": c.commitment_date.isoformat() if c.commitment_date else None,
        "supplier_status": c.supplier_status,
        "supplier_remark": c.supplier_remark,
        "reply_mail_id": c.reply_mail_id,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _norm_identity(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def _is_valid_commitment_row(c: SupplierMaterialCommitment) -> bool:
    material_code = _norm_identity(c.material_code)
    material_name = _norm_identity(c.material_name)
    if not material_code and not material_name:
        return False
    header_like = [value for value in (material_code, material_name) if value in _HEADER_LIKE_VALUES]
    return len(header_like) < max(1, len([value for value in (material_code, material_name) if value]))


def _load_commitments(
    db: Session, supplier_po_no: str
) -> dict[tuple[str, str], SupplierMaterialCommitment]:
    rows = db.scalars(
        select(SupplierMaterialCommitment)
        .where(SupplierMaterialCommitment.supplier_po_no == supplier_po_no)
        .order_by(SupplierMaterialCommitment.updated_at.desc())
    ).all()
    by_key: dict[tuple[str, str], SupplierMaterialCommitment] = {}
    for row in rows:
        if not _is_valid_commitment_row(row):
            continue
        key = (
            (row.material_code or "").strip().upper(),
            (row.material_name or "").strip().upper(),
        )
        if key not in by_key:
            by_key[key] = row
    return by_key


def _commitment_for_record(
    rec: ProcurementRecord,
    commitments: dict[tuple[str, str], SupplierMaterialCommitment],
) -> Optional[SupplierMaterialCommitment]:
    keys = [
        ("", (rec.material_name or "").strip().upper()),
        (
            (rec.crm_no or "").strip().upper(),
            (rec.material_name or "").strip().upper(),
        ),
    ]
    for key in keys:
        if key in commitments:
            return commitments[key]
    # fallback by material_name only across keys with any code
    name = (rec.material_name or "").strip().upper()
    for (code, mname), c in commitments.items():
        if mname == name:
            return c
    return None


def _material_line(
    rec: ProcurementRecord,
    commitment: Optional[SupplierMaterialCommitment],
) -> dict[str, Any]:
    signal = _norm_signal(rec.signal)
    pending = float(rec.qty) if rec.qty is not None else None
    return {
        "procurement_record_id": rec.id,
        "crm_no": rec.crm_no,
        "material_code": rec.crm_no,
        "material_name": rec.material_name,
        "po_qty": float(rec.qty) if rec.qty is not None else None,
        "pending_qty": pending,
        "uom": rec.uom,
        "due_date": rec.shipment_date.isoformat() if rec.shipment_date else None,
        "current_status": rec.po_status,
        "signal": signal,
        "followup_status": rec.followup_status,
        "ai_required": rec.ai_required,
        "last_supplier_reply": rec.last_supplier_reply,
        "commitment": _serialize_commitment(commitment) if commitment else None,
    }


def _supplier_meta(
    db: Session, supplier_name: Optional[str]
) -> tuple[Optional[int], list[str], list[str], list[str], list[str], bool]:
    if not supplier_name:
        return None, [], [], [], [], False
    sup = db.scalar(
        select(SupplierMaster).where(
            func.upper(SupplierMaster.supplier_name) == supplier_name.strip().upper()
        )
    )
    if not sup:
        return None, [], [], [], [], False
    mapping = db.scalar(
        select(SupplierEmail).where(
            SupplierEmail.supplier_id == sup.id,
            SupplierEmail.is_active.is_(True),
        )
    )
    if not mapping:
        return sup.id, [], [], [], [], False
    return (
        sup.id,
        list(mapping.to_emails or []),
        list(mapping.cc_emails or []),
        list(mapping.bcc_emails or []),
        list(mapping.escalation_emails or []),
        True,
    )


def build_po_group_payload(
    db: Session,
    records: list[ProcurementRecord],
    supplier_name: Optional[str],
    supplier_po_no: str,
) -> dict[str, Any]:
    """Common shape used by both the list aggregator and the detail endpoint."""
    if not records:
        return {}

    sorted_records = sorted(
        records, key=lambda r: (r.shipment_date or datetime.max, r.material_name or "")
    )
    commitments = _load_commitments(db, supplier_po_no)
    materials = [
        _material_line(rec, _commitment_for_record(rec, commitments))
        for rec in sorted_records
    ]
    overall_signal = highest_signal(rec.signal for rec in sorted_records)
    earliest_due = min(
        (r.shipment_date for r in sorted_records if r.shipment_date),
        default=None,
    )
    latest_followup = max(
        (r.last_followup_date for r in sorted_records if r.last_followup_date),
        default=None,
    )
    ai_required = any(r.ai_required for r in sorted_records)
    escalation_levels = {r.escalation_level for r in sorted_records if r.escalation_level}

    (
        supplier_id,
        to_emails,
        cc_emails,
        bcc_emails,
        escalation_emails,
        mapping_active,
    ) = _supplier_meta(db, supplier_name)

    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "supplier_po_no": supplier_po_no,
        "material_count": len(materials),
        "overall_signal": overall_signal,
        "earliest_due_date": earliest_due.isoformat() if earliest_due else None,
        "latest_followup_date": latest_followup.isoformat() if latest_followup else None,
        "escalation_levels": sorted(escalation_levels),
        "ai_required": ai_required,
        "mapping_active": mapping_active,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "escalation_emails": escalation_emails,
        "procurement_record_ids": [r.id for r in sorted_records],
        "anchor_record_id": sorted_records[0].id,
        "materials": materials,
    }


def list_po_groups(
    db: Session,
    *,
    signal: Optional[str] = None,
    supplier_name: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    size: int = 25,
) -> dict[str, Any]:
    stmt = select(ProcurementRecord)
    if signal:
        stmt = stmt.where(func.upper(ProcurementRecord.signal) == signal.strip().upper())
    if supplier_name:
        stmt = stmt.where(
            func.upper(ProcurementRecord.supplier_name) == supplier_name.strip().upper()
        )
    if supplier_po_no:
        stmt = stmt.where(ProcurementRecord.supplier_po_no == supplier_po_no.strip())
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ProcurementRecord.supplier_po_no.ilike(like),
                ProcurementRecord.crm_no.ilike(like),
                ProcurementRecord.supplier_name.ilike(like),
                ProcurementRecord.material_name.ilike(like),
            )
        )

    records = db.scalars(stmt).all()

    buckets: dict[tuple[str, str], list[ProcurementRecord]] = {}
    for rec in records:
        if not rec.supplier_po_no:
            continue
        buckets.setdefault(_group_key(rec), []).append(rec)

    groups: list[dict[str, Any]] = []
    for (_, _), items in buckets.items():
        first = items[0]
        groups.append(
            build_po_group_payload(
                db, items, first.supplier_name, first.supplier_po_no
            )
        )

    rank_dir = {"BLACK": 0, "RED": 1, "YELLOW": 2, "GREEN": 3}
    groups.sort(
        key=lambda g: (
            rank_dir.get(g.get("overall_signal", "GREEN"), 3),
            g.get("earliest_due_date") or "9999-99-99",
            g.get("supplier_name") or "",
        )
    )

    total = len(groups)
    page = max(page, 1)
    size = max(min(size, 200), 1)
    start = (page - 1) * size
    end = start + size

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": groups[start:end],
    }


def get_po_group(
    db: Session, supplier_name: str, supplier_po_no: str
) -> Optional[dict[str, Any]]:
    upper = supplier_name.strip().upper()
    po = supplier_po_no.strip()
    records = db.scalars(
        select(ProcurementRecord).where(
            func.upper(ProcurementRecord.supplier_name) == upper,
            ProcurementRecord.supplier_po_no == po,
        )
    ).all()
    if not records:
        return None
    return build_po_group_payload(db, records, records[0].supplier_name, po)


def find_today_draft(
    db: Session,
    *,
    supplier_name: Optional[str],
    supplier_po_no: str,
    mail_type: str,
) -> Optional[MailHistory]:
    """Return an existing PO-wise DRAFT/SENT mail from today for the same supplier+PO+mail_type."""
    if not supplier_po_no or not mail_type:
        return None
    midnight = datetime.combine(date.today(), datetime.min.time())
    tomorrow = midnight + timedelta(days=1)
    stmt = (
        select(MailHistory)
        .where(
            MailHistory.supplier_po_no == supplier_po_no.strip(),
            MailHistory.mail_type == mail_type,
            # Only reuse a live draft/sent mail — never a FAILED/CANCELLED one,
            # so regenerating after a failure produces a fresh mail.
            MailHistory.sent_status.in_(["READY", "SENT"]),
            MailHistory.created_at >= midnight,
            MailHistory.created_at < tomorrow,
        )
        .order_by(MailHistory.created_at.desc())
    )
    if supplier_name:
        stmt = stmt.where(
            func.upper(MailHistory.supplier_name) == supplier_name.strip().upper()
        )
    return db.scalar(stmt)


def list_commitments(
    db: Session,
    *,
    supplier_po_no: Optional[str] = None,
    supplier_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    stmt = select(SupplierMaterialCommitment)
    if supplier_po_no:
        stmt = stmt.where(SupplierMaterialCommitment.supplier_po_no == supplier_po_no.strip())
    if supplier_name:
        stmt = stmt.where(
            func.upper(SupplierMaterialCommitment.supplier_name)
            == supplier_name.strip().upper()
        )
    stmt = stmt.order_by(SupplierMaterialCommitment.updated_at.desc())
    return [
        _serialize_commitment(c)
        for c in db.scalars(stmt).all()
        if _is_valid_commitment_row(c)
    ]


def upsert_commitment(
    db: Session,
    *,
    supplier_po_no: str,
    material_name: str,
    procurement_record_id: Optional[int],
    supplier_id: Optional[int],
    supplier_name: Optional[str],
    material_code: Optional[str],
    commitment_qty: Optional[float],
    commitment_date_value: Optional[date],
    supplier_status: Optional[str],
    supplier_remark: Optional[str],
    reply_mail_id: Optional[int],
    commit: bool = True,
) -> SupplierMaterialCommitment:
    row = db.scalar(
        select(SupplierMaterialCommitment).where(
            SupplierMaterialCommitment.supplier_po_no == supplier_po_no.strip(),
            func.upper(SupplierMaterialCommitment.material_name)
            == material_name.strip().upper(),
        )
    )
    if row is None:
        row = SupplierMaterialCommitment(
            supplier_po_no=supplier_po_no.strip(),
            material_name=material_name.strip(),
        )
        db.add(row)

    row.procurement_record_id = procurement_record_id or row.procurement_record_id
    row.supplier_id = supplier_id or row.supplier_id
    row.supplier_name = supplier_name or row.supplier_name
    row.material_code = material_code or row.material_code
    if commitment_qty is not None:
        row.commitment_qty = commitment_qty
    if commitment_date_value is not None:
        row.commitment_date = commitment_date_value
    if supplier_status:
        row.supplier_status = supplier_status
    if supplier_remark:
        row.supplier_remark = supplier_remark
    if reply_mail_id:
        row.reply_mail_id = reply_mail_id

    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row
