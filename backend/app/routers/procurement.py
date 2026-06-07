from datetime import date, datetime
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from openpyxl import load_workbook
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.procurement import ProcurementRecord
from ..schemas.procurement import (
    ProcurementCreate, ProcurementUpdate, ProcurementOut,
    ProcurementListOut, ProcurementSyncSummary, DashboardKpis,
)
from ..services.procurement_sync_service import (
    ACCEPTED_EXCEL_COLUMNS,
    COLUMN_ALIASES,
    normalize_excel_headers,
    row_from_excel,
    sync_procurement_rows,
)
from ..services.followup_engine import apply_followup_logic

router = APIRouter(prefix="/api/procurement", tags=["procurement"])

SAMPLE_DATA_PATH = Path(__file__).resolve().parents[2] / "sample_data" / "procurement_sample.json"


@router.get("/dashboard", response_model=DashboardKpis)
def dashboard(db: Session = Depends(get_db)):
    R = ProcurementRecord
    today = date.today()

    def n(stmt) -> int:
        return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    return DashboardKpis(
        total_records=n(select(R)),
        green_count=n(select(R).where(R.signal == "GREEN")),
        yellow_count=n(select(R).where(R.signal == "YELLOW")),
        red_count=n(select(R).where(R.signal == "RED")),
        black_count=n(select(R).where(R.signal == "BLACK")),
        overdue_count=n(select(R).where(R.shipment_date < datetime.combine(today, datetime.min.time()))),
        due_today_count=n(select(R).where(
            R.shipment_date >= datetime.combine(today, datetime.min.time()),
            R.shipment_date < datetime.combine(today, datetime.max.time()),
        )),
        ai_required_count=n(select(R).where(R.ai_required.is_(True))),
    )


@router.get("", response_model=ProcurementListOut)
def list_records(
    db: Session = Depends(get_db),
    signal: Optional[str] = None,
    supplier_name: Optional[str] = None,
    po_no: Optional[str] = None,
    supplier_po_no: Optional[str] = None,
    crm_no: Optional[str] = None,
    po_status: Optional[str] = None,
    shipment_date_from: Optional[date] = None,
    shipment_date_to: Optional[date] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
):
    R = ProcurementRecord
    stmt = select(R)
    if signal: stmt = stmt.where(R.signal == signal.upper())
    if supplier_name: stmt = stmt.where(R.supplier_name.ilike(f"%{supplier_name}%"))
    supplier_po_filter = supplier_po_no or po_no
    if supplier_po_filter: stmt = stmt.where(R.supplier_po_no.ilike(f"%{supplier_po_filter}%"))
    if crm_no: stmt = stmt.where(R.crm_no.ilike(f"%{crm_no}%"))
    if po_status: stmt = stmt.where(R.po_status == po_status)
    if shipment_date_from:
        stmt = stmt.where(R.shipment_date >= datetime.combine(shipment_date_from, datetime.min.time()))
    if shipment_date_to:
        stmt = stmt.where(R.shipment_date <= datetime.combine(shipment_date_to, datetime.max.time()))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(
            R.crm_no.ilike(like),
            R.supplier_po_no.ilike(like),
            R.material_name.ilike(like),
            R.supplier_name.ilike(like),
            R.po_status.ilike(like),
            R.signal.ilike(like),
        ))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(R.shipment_date.asc().nulls_last() if hasattr(R.shipment_date, "asc") else R.id.desc())
            .offset((page - 1) * size).limit(size)
    ).all()
    return ProcurementListOut(total=total, page=page, size=size, items=rows)


@router.get("/columns")
def columns():
    return {
        "unique_key": ["crm_no", "supplier_po_no", "material_name"],
        "excel_columns": ACCEPTED_EXCEL_COLUMNS,
        "field_names": list(ProcurementCreate.model_fields.keys()),
        "aliases": COLUMN_ALIASES,
        "notes": {"po_no": "Deprecated alias. It maps to supplier_po_no for backward-compatible JSON only."},
    }


@router.get("/{rec_id}", response_model=ProcurementOut)
def get_one(rec_id: int, db: Session = Depends(get_db)):
    rec = db.get(ProcurementRecord, rec_id)
    if not rec:
        raise HTTPException(404, "Not found")
    return rec


@router.post("/sync", response_model=ProcurementSyncSummary)
def sync_endpoint(payload: list[dict[str, Any]], db: Session = Depends(get_db)):
    return sync_procurement_rows(db, payload, source="json")


@router.post("/upload-excel", response_model=ProcurementSyncSummary)
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Only .xlsx files are supported")

    try:
        workbook = load_workbook(BytesIO(await file.read()), read_only=True, data_only=True)
        sheet = workbook.active
        rows_iter = sheet.iter_rows(values_only=True)
        raw_headers = next(rows_iter, None)
        if not raw_headers:
            raise HTTPException(400, "Excel file is empty")
        headers = normalize_excel_headers(raw_headers)
        rows = [row_from_excel(headers, values) for values in rows_iter if any(v is not None for v in values)]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Unable to read Excel file: {exc}") from exc

    return sync_procurement_rows(db, rows, source="excel")


@router.post("/load-sample-data", response_model=ProcurementSyncSummary)
def load_sample_data(db: Session = Depends(get_db)):
    if not SAMPLE_DATA_PATH.exists():
        raise HTTPException(404, f"Sample data file not found: {SAMPLE_DATA_PATH}")
    with SAMPLE_DATA_PATH.open("r", encoding="utf-8") as fh:
        rows = json.load(fh)
    if not isinstance(rows, list):
        raise HTTPException(400, "Sample data must be a JSON array")
    return sync_procurement_rows(db, rows, source="sample")


@router.put("/{rec_id}", response_model=ProcurementOut)
def update_record(rec_id: int, payload: ProcurementUpdate, db: Session = Depends(get_db)):
    rec = db.get(ProcurementRecord, rec_id)
    if not rec:
        raise HTTPException(404, "Not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rec, k, v)
    apply_followup_logic(rec)
    db.commit()
    db.refresh(rec)
    return rec
