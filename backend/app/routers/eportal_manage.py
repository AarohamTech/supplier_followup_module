"""Employee-portal access to two staff admin screens: Supplier Assignment and
Email Master.

Each screen is gated by a per-employee permission flag on `users`
(services/employee_permissions.py). Both flags are granted by default; an admin
switches them off per employee on Employee Logins. The flag is enforced here,
server-side, on every route. The handlers reuse the staff routers' logic so the
two portals behave the same; staff routes are unchanged.

What an employee with the flag can do:
- Supplier Assignment: list suppliers with their assignees and change them
  (staff need manager+ for the change).
- Email Master: list, add and edit supplier email mappings (an edit can also
  deactivate a mapping). Deleting a mapping, managing supplier portal logins
  and the change log stay admin-only, as on the staff side.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import get_current_employee
from ..database import get_db
from ..models.supplier import SupplierMaster
from ..models.user import User
from ..schemas.supplier_email import SupplierEmailCreate, SupplierEmailOut, SupplierEmailUpdate
from ..services import employee_permissions as perms
from ..services import supplier_assignment_service as assign_svc
from . import supplier_assignments as staff_assignments
from . import supplier_emails as staff_emails

router = APIRouter(prefix="/api/eportal/manage", tags=["eportal-manage"])


def _require(flag: str, label: str):
    def _guard(user: User = Depends(get_current_employee)) -> User:
        if not perms.has_permission(user, flag):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your account does not have access to {label}. Ask an admin to enable it.",
            )
        return user

    return _guard


require_assignments = _require(perms.SUPPLIER_ASSIGNMENTS, "Supplier Assignment")
require_email_master = _require(perms.EMAIL_MASTER, "Email Master")


# ── Supplier Assignment ──────────────────────────────────────────────────────
@router.get("/supplier-assignments")
def list_assignments(
    db: Session = Depends(get_db),
    _user: User = Depends(require_assignments),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> dict:
    suppliers, total = assign_svc.list_page(db, search=search, page=page, size=size)
    return {"suppliers": suppliers, "total": total, "page": page, "size": size}


@router.get("/supplier-assignments/assignable-users")
def assignable_users(
    db: Session = Depends(get_db), _user: User = Depends(require_assignments)
) -> dict:
    return staff_assignments.assignable_users(db=db)


@router.put("/supplier-assignments/{supplier_id}")
def set_assignees(
    supplier_id: int,
    payload: staff_assignments.AssigneesPayload,
    db: Session = Depends(get_db),
    _user: User = Depends(require_assignments),
) -> dict:
    return staff_assignments.set_assignees(supplier_id=supplier_id, payload=payload, db=db)


# ── Email Master ─────────────────────────────────────────────────────────────
@router.get("/suppliers")
def list_suppliers(
    db: Session = Depends(get_db), _user: User = Depends(require_email_master)
) -> list[dict]:
    """Supplier dropdown for the mapping editor (id + name only)."""
    rows = db.scalars(select(SupplierMaster).order_by(SupplierMaster.supplier_name)).all()
    return [
        {"id": r.id, "supplier_name": r.supplier_name, "is_active": bool(r.is_active)}
        for r in rows
    ]


@router.get("/supplier-emails", response_model=list[SupplierEmailOut])
def list_emails(db: Session = Depends(get_db), _user: User = Depends(require_email_master)):
    return staff_emails.list_emails(db=db, scope=None)


@router.post("/supplier-emails", response_model=SupplierEmailOut, status_code=201)
def create_email(
    payload: SupplierEmailCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_email_master),
):
    return staff_emails.create(payload=payload, db=db, actor=user, scope=None)


@router.put("/supplier-emails/{eid}", response_model=SupplierEmailOut)
def update_email(
    eid: int,
    payload: SupplierEmailUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_email_master),
):
    return staff_emails.update(eid=eid, payload=payload, db=db, actor=user)
