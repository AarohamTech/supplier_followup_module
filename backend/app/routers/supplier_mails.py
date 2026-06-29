"""Supplier Inbox router — read-only list + detail of incoming supplier mail."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import supplier_inbox_service as svc

router = APIRouter(prefix="/api/supplier-mails", tags=["supplier-mails"])


class SupplierMailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier_po_no: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    sender_email: Optional[str] = None
    receiver_email: Optional[str] = None
    status: Optional[str] = None
    parsed_status: Optional[str] = None
    received_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class SupplierMailListResponse(BaseModel):
    items: list[SupplierMailOut]
    total: int


@router.get("", response_model=SupplierMailListResponse)
def list_supplier_mails(
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows, total = svc.list_supplier_inbox(db, search=search, limit=limit, offset=offset)
    return SupplierMailListResponse(
        items=[SupplierMailOut.model_validate(r) for r in rows], total=total
    )


@router.get("/{message_id}", response_model=SupplierMailOut)
def get_supplier_mail(message_id: int, db: Session = Depends(get_db)):
    row = svc.get_message(db, message_id)
    if row is None:
        raise HTTPException(404, "Supplier mail not found")
    return SupplierMailOut.model_validate(row)
