from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.supplier import SupplierMaster
from ..models.supplier_email import SupplierEmail
from ..schemas.supplier import SupplierOut, SupplierUpdate

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


def _primary_email(mapping: SupplierEmail | None) -> str | None:
    if not mapping or not mapping.to_emails:
        return None
    return mapping.to_emails[0]


def _to_out(row: SupplierMaster, mapping: SupplierEmail | None = None) -> dict:
    return {
        "id": row.id,
        "supplier_name": row.supplier_name,
        "latest_supplier_po_no": row.latest_supplier_po_no,
        "latest_signal": row.latest_signal,
        "is_active": row.is_active,
        "email_mapped": bool(mapping),
        "primary_email": _primary_email(mapping),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db)):
    suppliers = db.scalars(select(SupplierMaster).order_by(SupplierMaster.supplier_name)).all()
    mappings = db.scalars(
        select(SupplierEmail).where(SupplierEmail.is_active.is_(True))
    ).all()
    mapping_by_supplier = {m.supplier_id: m for m in mappings}
    return [_to_out(row, mapping_by_supplier.get(row.id)) for row in suppliers]


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db)):
    row = db.get(SupplierMaster, supplier_id)
    if not row:
        raise HTTPException(404, "Supplier not found")
    mapping = db.scalar(
        select(SupplierEmail).where(
            SupplierEmail.supplier_id == row.id,
            SupplierEmail.is_active.is_(True),
        )
    )
    return _to_out(row, mapping)


@router.put("/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db)):
    row = db.get(SupplierMaster, supplier_id)
    if not row:
        raise HTTPException(404, "Supplier not found")

    data = payload.model_dump(exclude_unset=True)
    if "supplier_name" in data and data["supplier_name"]:
        name = data["supplier_name"].strip()
        duplicate = db.scalar(
            select(SupplierMaster).where(
                SupplierMaster.supplier_name == name,
                SupplierMaster.id != row.id,
            )
        )
        if duplicate:
            raise HTTPException(409, "Supplier name already exists")
        row.supplier_name = name
        for mapping in db.scalars(select(SupplierEmail).where(SupplierEmail.supplier_id == row.id)):
            mapping.supplier_name = name
    if "is_active" in data:
        row.is_active = bool(data["is_active"])

    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return get_supplier(row.id, db)
