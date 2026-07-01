from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _parse_date(v: Any) -> Any:
    if v in (None, "", "null"):
        return None
    if isinstance(v, (date, datetime)):
        return v
    if isinstance(v, str):
        s = v.strip()
        for fmt in (
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%d-%m-%Y %H:%M",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return v


class ProcurementBase(BaseModel):
    crm_no: str
    material_name: str
    uom: Optional[str] = None
    lead_time: Optional[int] = None
    shipment_date: Optional[datetime] = None
    signal: Optional[str] = None
    stock: Optional[float] = None
    qty: Optional[float] = None
    po_status: Optional[str] = None
    adv_status: Optional[str] = None
    supplier_po_no: str
    supplier_date: Optional[date] = None
    supplier_name: Optional[str] = None
    quantity: Optional[float] = None
    rate: Optional[float] = None
    owner_emp_code: Optional[str] = None

    @field_validator("supplier_date", mode="before")
    @classmethod
    def _v_dates(cls, v):
        d = _parse_date(v)
        if isinstance(d, datetime):
            return d.date()
        return d

    @field_validator("shipment_date", mode="before")
    @classmethod
    def _v_datetimes(cls, v):
        return _parse_date(v)

    @field_validator("signal", mode="before")
    @classmethod
    def _v_signal(cls, v):
        if v in (None, ""):
            return None
        return str(v).strip().upper()


class ProcurementCreate(ProcurementBase):
    pass


class ProcurementUpdate(BaseModel):
    shipment_date: Optional[datetime] = None
    signal: Optional[str] = None
    stock: Optional[float] = None
    qty: Optional[float] = None
    po_status: Optional[str] = None
    adv_status: Optional[str] = None
    quantity: Optional[float] = None
    rate: Optional[float] = None
    followup_status: Optional[str] = None
    mail_status: Optional[str] = None
    last_supplier_reply: Optional[str] = None
    commitment_date: Optional[date] = None
    delay_reason: Optional[str] = None
    escalation_level: Optional[str] = None
    ai_required: Optional[bool] = None
    next_followup_date: Optional[datetime] = None


class ProcurementOut(ProcurementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    followup_status: str
    mail_status: str
    followup_count: int
    last_followup_date: Optional[datetime] = None
    last_supplier_reply: Optional[str] = None
    commitment_date: Optional[date] = None
    delay_reason: Optional[str] = None
    escalation_level: str
    ai_required: bool
    next_followup_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ProcurementListOut(BaseModel):
    total: int
    page: int
    size: int
    items: list[ProcurementOut]


class SyncError(BaseModel):
    row_index: int
    error: str


class ProcurementSyncSummary(BaseModel):
    source: str
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    errors: list[SyncError] = []


SyncResult = ProcurementSyncSummary
ProcurementResponse = ProcurementOut
ProcurementSyncRequest = list[dict[str, Any]]
ProcurementSyncResponse = ProcurementSyncSummary


class DashboardKpis(BaseModel):
    total_records: int
    green_count: int
    yellow_count: int
    red_count: int
    black_count: int
    overdue_count: int
    due_today_count: int
    ai_required_count: int


class SupplierSlice(BaseModel):
    name: str
    count: int


class ProcurementBreakdown(BaseModel):
    """Dashboard aggregations under the active filters: signal counts, the
    open/not-delivered ("pending") count, and the supplier distribution
    (top suppliers + an aggregated "Others" slice)."""
    total: int
    green_count: int
    yellow_count: int
    red_count: int
    black_count: int
    pending_count: int
    by_supplier: list[SupplierSlice]


class CrmIngestLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ran_at: datetime
    status: str
    trigger: str
    desk: Optional[str] = None
    fetched: int
    generated: int
    created: int
    updated: int
    skipped: int
    errors: int
    duration_ms: Optional[int] = None
    message: Optional[str] = None
