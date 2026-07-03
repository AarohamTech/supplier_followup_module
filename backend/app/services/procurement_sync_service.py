"""Procurement intake service shared by Excel, dummy JSON, and future ERP APIs."""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.procurement import ProcurementRecord
from ..models.supplier import SupplierMaster
from ..schemas.procurement import ProcurementCreate, ProcurementSyncSummary, SyncError
from .followup_engine import apply_followup_logic

log = logging.getLogger(__name__)

REQUIRED_KEY_FIELDS = ("crm_no", "supplier_po_no", "material_name")
DATE_FIELDS = {"supplier_date", "po_date"}
DATETIME_FIELDS = {"shipment_date"}
NUMERIC_FIELDS = {"stock", "qty", "quantity", "rate"}
INTEGER_FIELDS = {"lead_time"}
STRING_FIELDS = {
    "crm_no",
    "material_name",
    "uom",
    "signal",
    "po_status",
    "adv_status",
    "supplier_po_no",
    "supplier_name",
    "owner_emp_code",
    "customer_name",
    "customer_po_no",
}

UPDATABLE_FROM_SOURCE = (
    "uom", "lead_time", "shipment_date", "signal", "stock", "qty",
    "po_status", "adv_status", "supplier_date", "supplier_name", "quantity", "rate",
    "owner_emp_code",
)

ACCEPTED_EXCEL_COLUMNS = [
    "CRM no.",
    "Material Name",
    "Uom",
    "Lead T",
    "Shipment Date",
    "Signal",
    "Stock",
    "Qty",
    "PO Status",
    "Adv. Status",
    "Supplier Po No",
    "Supplier Date",
    "Supplier Name",
    "Quantity",
    "Rate",
]

COLUMN_ALIASES = {
    "crm no.": "crm_no",
    "crm no": "crm_no",
    "crm_no": "crm_no",
    "crm no": "crm_no",
    "crmno": "crm_no",
    "material name": "material_name",
    "material_name": "material_name",
    "uom": "uom",
    "lead t": "lead_time",
    "lead time": "lead_time",
    "lead_time": "lead_time",
    "shipment date": "shipment_date",
    "shipment_date": "shipment_date",
    "signal": "signal",
    "stock": "stock",
    "qty": "qty",
    "po status": "po_status",
    "po_status": "po_status",
    "adv. status": "adv_status",
    "adv status": "adv_status",
    "adv_status": "adv_status",
    "supplier po no": "supplier_po_no",
    "supplier po no.": "supplier_po_no",
    "supplier_po_no": "supplier_po_no",
    "supplier date": "supplier_date",
    "supplier_date": "supplier_date",
    "supplier name": "supplier_name",
    "supplier_name": "supplier_name",
    "quantity": "quantity",
    "rate": "rate",
    # Backward-compatible JSON aliases from the old prototype.
    "po no": "supplier_po_no",
    "po no.": "supplier_po_no",
    "po_no": "supplier_po_no",
    "supplier quantity": "quantity",
    "supplier_quantity": "quantity",
}

DATE_FORMATS = (
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
)


def normalize_header(header: Any) -> str:
    key = str(header or "").strip().replace("\n", " ")
    key = " ".join(key.split()).lower()
    return COLUMN_ALIASES.get(key, key.replace(" ", "_").replace(".", ""))


def normalize_excel_headers(headers: Iterable[Any]) -> list[str | None]:
    out: list[str | None] = []
    for header in headers:
        raw = str(header or "").strip()
        out.append(normalize_header(raw) if raw else None)
    return out


def row_from_excel(headers: list[str | None], values: Iterable[Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field, value in zip(headers, values):
        if field:
            row[field] = value
    return row


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in {"", "-", "--", "null", "None", "none", "N/A", "n/a"}:
            return None
        return stripped
    return value


def _parse_date_value(value: Any, field: str) -> date | datetime | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if field in DATETIME_FIELDS else value.date()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()) if field in DATETIME_FIELDS else value
    if isinstance(value, str):
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed if field in DATETIME_FIELDS else parsed.date()
            except ValueError:
                continue
    raise ValueError(f"Invalid date for {field}: {value}")


def _parse_number(value: Any, field: str) -> int | float | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid numeric for {field}: {value}")
    if isinstance(value, (int, float, Decimal)):
        return int(value) if field in INTEGER_FIELDS else float(value)
    if isinstance(value, str):
        try:
            parsed = Decimal(value.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid numeric for {field}: {value}") from exc
        return int(parsed) if field in INTEGER_FIELDS else float(parsed)
    raise ValueError(f"Invalid numeric for {field}: {value}")


def _parse_text(value: Any) -> str | None:
    value = _blank_to_none(value)
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace("\xa0", " ").strip()


def normalize_procurement_row(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    normalized: dict[str, Any] = {}
    errors: list[str] = []

    for key, value in raw.items():
        field = normalize_header(key)
        if field not in ProcurementCreate.model_fields:
            continue
        try:
            if field in DATE_FIELDS or field in DATETIME_FIELDS:
                normalized[field] = _parse_date_value(value, field)
            elif field in NUMERIC_FIELDS or field in INTEGER_FIELDS:
                normalized[field] = _parse_number(value, field)
            elif field == "signal":
                cleaned = _parse_text(value)
                normalized[field] = str(cleaned).upper() if cleaned is not None else None
            elif field in STRING_FIELDS:
                normalized[field] = _parse_text(value)
            else:
                normalized[field] = _blank_to_none(value)
        except ValueError as exc:
            errors.append(str(exc))

    for field in REQUIRED_KEY_FIELDS:
        if not normalized.get(field):
            errors.append(f"Missing {field}")

    return (None, errors) if errors else (normalized, [])


def _find(db: Session, payload: ProcurementCreate) -> ProcurementRecord | None:
    return db.scalar(
        select(ProcurementRecord).where(
            ProcurementRecord.crm_no == payload.crm_no,
            ProcurementRecord.supplier_po_no == payload.supplier_po_no,
            ProcurementRecord.material_name == payload.material_name,
        )
    )


def upsert_one(db: Session, payload: ProcurementCreate) -> tuple[ProcurementRecord, str]:
    existing = _find(db, payload)
    if existing is None:
        data = payload.model_dump()
        # po_no holds the CUSTOMER PO (falls back to supplier PO when the feed
        # has no customer PO); the column is also NOT NULL on old SQLite DBs.
        data.pop("customer_po_no", None)
        data["po_no"] = payload.customer_po_no or payload.supplier_po_no
        rec = ProcurementRecord(**data)
        apply_followup_logic(rec)
        db.add(rec)
        db.flush()
        return rec, "created"

    changed = False
    for field in UPDATABLE_FROM_SOURCE:
        new_val = getattr(payload, field, None)
        if new_val is not None and getattr(existing, field) != new_val:
            setattr(existing, field, new_val)
            changed = True

    customer_po = payload.customer_po_no or payload.supplier_po_no
    if existing.po_no != customer_po:
        existing.po_no = customer_po
        changed = True
    for field in ("customer_name", "po_date"):
        new_val = getattr(payload, field, None)
        if new_val is not None and getattr(existing, field) != new_val:
            setattr(existing, field, new_val)
            changed = True

    if changed:
        existing.updated_at = datetime.utcnow()
        apply_followup_logic(existing)
        db.flush()
        return existing, "updated"
    return existing, "skipped"


def sync_supplier_from_record(db: Session, rec: ProcurementRecord) -> SupplierMaster | None:
    if not rec.supplier_name:
        return None

    supplier = db.scalar(
        select(SupplierMaster).where(SupplierMaster.supplier_name == rec.supplier_name)
    )
    if supplier is None:
        supplier = SupplierMaster(
            supplier_name=rec.supplier_name,
            latest_supplier_po_no=rec.supplier_po_no,
            latest_signal=rec.signal,
            is_active=True,
        )
        db.add(supplier)
    else:
        supplier.latest_supplier_po_no = rec.supplier_po_no
        supplier.latest_signal = rec.signal
        supplier.updated_at = datetime.utcnow()
    db.flush()
    return supplier


def _validation_errors(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
    )


def sync_procurement_rows(
    db: Session,
    rows: list[dict[str, Any]],
    source: str = "manual",
) -> ProcurementSyncSummary:
    created = updated = skipped = 0
    errors: list[SyncError] = []

    for index, raw in enumerate(rows, start=1):
        normalized, row_errors = normalize_procurement_row(raw)
        if row_errors or normalized is None:
            skipped += 1
            errors.append(SyncError(row_index=index, error="; ".join(row_errors)))
            continue

        try:
            payload = ProcurementCreate(**normalized)
            rec, action = upsert_one(db, payload)
            sync_supplier_from_record(db, rec)
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
        except ValidationError as exc:
            skipped += 1
            errors.append(SyncError(row_index=index, error=_validation_errors(exc)))
        except Exception as exc:  # noqa: BLE001
            log.exception("sync row failed")
            skipped += 1
            errors.append(SyncError(row_index=index, error=str(exc)))

    db.commit()
    return ProcurementSyncSummary(
        source=source,
        created_count=created,
        updated_count=updated,
        skipped_count=skipped,
        error_count=len(errors),
        errors=errors,
    )


def sync_records(db: Session, payloads: Iterable[ProcurementCreate]) -> ProcurementSyncSummary:
    rows = [payload.model_dump() if isinstance(payload, ProcurementCreate) else dict(payload) for payload in payloads]
    return sync_procurement_rows(db, rows, source="manual")
