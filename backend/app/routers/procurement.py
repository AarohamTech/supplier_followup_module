from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from ..core.deps import require_admin, require_manager
from ..database import get_db
from ..models.crm_ingest_log import CrmIngestLog
from ..models.procurement import ProcurementRecord
from ..schemas.procurement import (
    ProcurementCreate, ProcurementUpdate, ProcurementOut,
    ProcurementListOut, ProcurementSyncSummary, DashboardKpis, CrmIngestLogOut,
)
from ..services.procurement_sync_service import (
    ACCEPTED_EXCEL_COLUMNS,
    COLUMN_ALIASES,
    sync_procurement_rows,
)
from ..services.followup_engine import apply_followup_logic
from ..services import crm_ingest_service

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


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


@router.get(
    "/crm-ingestion-logs",
    response_model=list[CrmIngestLogOut],
    dependencies=[Depends(require_admin)],
)
def crm_ingestion_logs(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
) -> list[CrmIngestLog]:
    """Admin-only CRM fetch history: how many POs were fetched / added / changed."""
    return list(
        db.scalars(select(CrmIngestLog).order_by(CrmIngestLog.ran_at.desc()).limit(limit)).all()
    )


@router.get("/{rec_id}", response_model=ProcurementOut)
def get_one(rec_id: int, db: Session = Depends(get_db)):
    rec = db.get(ProcurementRecord, rec_id)
    if not rec:
        raise HTTPException(404, "Not found")
    return rec


@router.post("/sync", response_model=ProcurementSyncSummary)
def sync_endpoint(payload: list[dict[str, Any]], db: Session = Depends(get_db)):
    return sync_procurement_rows(db, payload, source="json")


@router.post("/crm-sync", dependencies=[Depends(require_manager)])
def crm_sync_now(db: Session = Depends(get_db)) -> dict:
    """Manually trigger a live CRM ingestion run (manager+). Records a fetch log."""
    return crm_ingest_service.poll_and_ingest(db, trigger="manual")


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
