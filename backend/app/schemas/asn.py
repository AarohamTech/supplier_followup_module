"""Pydantic DTOs for the ASN (Advance Shipping Notice) feature."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Inputs ────────────────────────────────────────────────────────────────────
class AsnItemIn(BaseModel):
    procurement_record_id: Optional[int] = None
    material_name: str = Field(min_length=1, max_length=500)
    material_code: Optional[str] = None
    qty_shipped: Optional[float] = None
    uom: Optional[str] = None


class AsnCreate(BaseModel):
    supplier_po_no: str = Field(min_length=1, max_length=64)
    crm_no: Optional[str] = None
    carrier_name: Optional[str] = None
    tracking_no: Optional[str] = None
    transport_mode: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    eta: Optional[datetime] = None
    remarks: Optional[str] = None
    items: list[AsnItemIn] = Field(default_factory=list)
    # False → save as Draft; True → submit (status SUBMITTED).
    submit: bool = False


class AsnUpdate(BaseModel):
    supplier_po_no: Optional[str] = None
    crm_no: Optional[str] = None
    carrier_name: Optional[str] = None
    tracking_no: Optional[str] = None
    transport_mode: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    eta: Optional[datetime] = None
    remarks: Optional[str] = None
    alert: Optional[bool] = None
    alert_reason: Optional[str] = None
    submit: Optional[bool] = None


class AsnEventIn(BaseModel):
    stage: str = Field(min_length=1, max_length=24)
    location: Optional[str] = None
    note: Optional[str] = None
    label: Optional[str] = None
    alert: Optional[bool] = None
    alert_reason: Optional[str] = None
    occurred_at: Optional[datetime] = None


# ── Outputs ───────────────────────────────────────────────────────────────────
class AsnItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    procurement_record_id: Optional[int] = None
    material_name: str
    material_code: Optional[str] = None
    qty_shipped: Optional[float] = None
    uom: Optional[str] = None


class AsnEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    stage: str
    status_label: Optional[str] = None
    location: Optional[str] = None
    note: Optional[str] = None
    occurred_at: datetime
    created_by: Optional[str] = None


class AsnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    asn_no: str
    supplier_id: int
    supplier_name: Optional[str] = None
    supplier_po_no: str
    crm_no: Optional[str] = None
    carrier_name: Optional[str] = None
    tracking_no: Optional[str] = None
    transport_mode: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    eta: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    status: str
    status_label: Optional[str] = None
    alert: bool
    alert_reason: Optional[str] = None
    progress_percent: int
    remarks: Optional[str] = None
    created_by_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: list[AsnItemOut] = Field(default_factory=list)
    events: list[AsnEventOut] = Field(default_factory=list)


class AsnSummaryOut(BaseModel):
    active: int
    pending: int
    urgent: int
    finalized: int
    total: int
    drafts: int


class AsnListOut(BaseModel):
    count: int
    items: list[AsnOut]
