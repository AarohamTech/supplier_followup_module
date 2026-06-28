from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import get_current_staff, require_admin
from ..database import get_db
from ..models.supplier import SupplierMaster
from ..models.supplier_email import SupplierEmail
from ..models.supplier_email_audit import SupplierEmailAudit
from ..models.user import User
from ..schemas.supplier_email import (
    SupplierEmailCreate,
    SupplierEmailUpdate,
    SupplierEmailOut,
    SupplierEmailAuditOut,
    LoginProvisioningSummary,
)
from ..services import supplier_account_service

router = APIRouter(prefix="/api/supplier-emails", tags=["supplier-emails"])

# Fields whose changes are tracked in the audit log.
_AUDITED = (
    "supplier_name", "to_emails", "cc_emails", "bcc_emails", "escalation_emails",
    "contact_person", "phone", "remarks", "is_active",
)


def _snapshot(row: SupplierEmail) -> dict:
    return {f: getattr(row, f) for f in _AUDITED}


def _actor_label(user: User) -> str:
    return user.full_name or user.username or user.email or f"user#{user.id}"


def _log_audit(
    db: Session, *, action: str, row: SupplierEmail, actor: User,
    changes: dict | None,
) -> None:
    """Append a change-log entry. For CREATE/DELETE `changes` is the full
    snapshot as {field: {"old"/"new": value}}; for UPDATE it's the diff."""
    db.add(SupplierEmailAudit(
        supplier_email_id=row.id,
        supplier_id=row.supplier_id,
        supplier_name=row.supplier_name,
        action=action,
        changed_by_id=actor.id,
        changed_by=_actor_label(actor),
        changes=changes or {},
    ))
    db.commit()


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


@router.get("/audit", response_model=list[SupplierEmailAuditOut])
def list_audit(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),  # admin-only change log
    limit: int = Query(200, ge=1, le=1000),
):
    """Who changed which mapping, and what changed. Admin-only."""
    return db.scalars(
        select(SupplierEmailAudit).order_by(SupplierEmailAudit.created_at.desc()).limit(limit)
    ).all()


@router.post("", response_model=SupplierEmailOut, status_code=201)
def create(
    payload: SupplierEmailCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
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
    _log_audit(
        db, action="CREATE", row=row, actor=actor,
        changes={f: {"old": None, "new": v} for f, v in _snapshot(row).items()},
    )
    summary = _provision_logins(db, row)
    return _out_with_provisioning(row, summary)


@router.put("/{eid}", response_model=SupplierEmailOut)
def update(
    eid: int,
    payload: SupplierEmailUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    row = db.get(SupplierEmail, eid)
    if not row:
        raise HTTPException(404, "Not found")

    before = _snapshot(row)
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
    after = _snapshot(row)
    diff = {f: {"old": before[f], "new": after[f]} for f in _AUDITED if before[f] != after[f]}
    if diff:
        _log_audit(db, action="UPDATE", row=row, actor=actor, changes=diff)
    summary = _provision_logins(db, row)
    return _out_with_provisioning(row, summary)


@router.delete("/{eid}", status_code=204)
def delete(
    eid: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),  # delete is admin-only
):
    row = db.get(SupplierEmail, eid)
    if not row:
        raise HTTPException(404, "Not found")
    supplier_id = row.supplier_id
    snapshot = {f: {"old": v, "new": None} for f, v in _snapshot(row).items()}
    # Log before the delete so the audit row carries the mapping's id + details.
    _log_audit(db, action="DELETE", row=row, actor=actor, changes=snapshot)
    db.delete(row)
    db.commit()
    # No mapping left → the supplier has no portal contacts; disable their logins.
    supplier_account_service.deactivate_supplier_logins(db, supplier_id)
    return None
