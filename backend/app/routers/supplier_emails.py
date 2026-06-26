from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.supplier import SupplierMaster
from ..models.supplier_email import SupplierEmail
from ..schemas.supplier_email import (
    SupplierEmailCreate,
    SupplierEmailUpdate,
    SupplierEmailOut,
    LoginProvisioningSummary,
)
from ..services import supplier_account_service

router = APIRouter(prefix="/api/supplier-emails", tags=["supplier-emails"])


def _provision_logins(db: Session, row: SupplierEmail) -> LoginProvisioningSummary:
    """Reconcile portal logins for the mapping and return the summary.

    An active mapping provisions a login per TO email; an inactive mapping
    deactivates all of the supplier's logins.
    """
    if row.is_active:
        summary = supplier_account_service.sync_supplier_logins(
            db,
            supplier_id=row.supplier_id,
            supplier_name=row.supplier_name,
            to_emails=list(row.to_emails or []),
        )
    else:
        disabled = supplier_account_service.deactivate_supplier_logins(db, row.supplier_id)
        summary = {"created": [], "reactivated": [], "deactivated": disabled,
                   "conflicts": [], "emailed": []}
    return LoginProvisioningSummary(**summary)


def _out_with_provisioning(row: SupplierEmail, summary: LoginProvisioningSummary) -> SupplierEmailOut:
    out = SupplierEmailOut.model_validate(row)
    out.provisioning = summary
    return out


def _active_mapping_exists(db: Session, supplier_id: int, except_id: int | None = None) -> bool:
    stmt = select(SupplierEmail).where(
        SupplierEmail.supplier_id == supplier_id,
        SupplierEmail.is_active.is_(True),
    )
    if except_id is not None:
        stmt = stmt.where(SupplierEmail.id != except_id)
    return db.scalar(stmt) is not None


def _load_supplier(db: Session, supplier_id: int) -> SupplierMaster:
    supplier = db.get(SupplierMaster, supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    if not supplier.is_active:
        raise HTTPException(400, "Supplier is inactive")
    return supplier


@router.get("", response_model=list[SupplierEmailOut])
def list_emails(db: Session = Depends(get_db)):
    return db.scalars(select(SupplierEmail).order_by(SupplierEmail.supplier_name)).all()


@router.post("", response_model=SupplierEmailOut, status_code=201)
def create(payload: SupplierEmailCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(mode="json")
    supplier = _load_supplier(db, data["supplier_id"])
    if not data.get("to_emails"):
        raise HTTPException(422, "At least one TO email is required")
    if data.get("is_active", True) and _active_mapping_exists(db, supplier.id):
        raise HTTPException(409, "Active email mapping already exists for this supplier")

    data["supplier_name"] = supplier.supplier_name
    row = SupplierEmail(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    summary = _provision_logins(db, row)
    return _out_with_provisioning(row, summary)


@router.put("/{eid}", response_model=SupplierEmailOut)
def update(eid: int, payload: SupplierEmailUpdate, db: Session = Depends(get_db)):
    row = db.get(SupplierEmail, eid)
    if not row:
        raise HTTPException(404, "Not found")

    data = payload.model_dump(exclude_unset=True, mode="json")
    supplier_id = data.get("supplier_id", row.supplier_id)
    supplier = _load_supplier(db, supplier_id)
    target_active = data.get("is_active", row.is_active)
    if target_active and _active_mapping_exists(db, supplier.id, except_id=row.id):
        raise HTTPException(409, "Active email mapping already exists for this supplier")
    if "to_emails" in data and not data["to_emails"]:
        raise HTTPException(422, "At least one TO email is required")

    data["supplier_id"] = supplier.id
    data["supplier_name"] = supplier.supplier_name
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    summary = _provision_logins(db, row)
    return _out_with_provisioning(row, summary)


@router.delete("/{eid}", status_code=204)
def delete(eid: int, db: Session = Depends(get_db)):
    row = db.get(SupplierEmail, eid)
    if not row:
        raise HTTPException(404, "Not found")
    supplier_id = row.supplier_id
    db.delete(row)
    db.commit()
    # No mapping left → the supplier has no portal contacts; disable their logins.
    supplier_account_service.deactivate_supplier_logins(db, supplier_id)
    return None
