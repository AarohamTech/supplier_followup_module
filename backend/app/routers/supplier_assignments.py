"""Supplier -> people assignment mapping.

Reads are open to any staff user; changing a supplier's assignees requires
manager+. Portal accounts are rejected at the app level (router mounted behind the
staff write-guard in main.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.deps import require_manager
from ..database import get_db
from ..models.supplier import SupplierMaster
from ..services import supplier_assignment_service as svc

router = APIRouter(prefix="/api/supplier-assignments", tags=["supplier-assignments"])

# Changing assignees requires manager+; reads stay open to any staff user.
_MGR = [Depends(require_manager)]


class AssigneesPayload(BaseModel):
    user_ids: list[int] = Field(default_factory=list)


@router.get("")
def list_assignments(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> dict:
    suppliers, total = svc.list_page(db, search=search, page=page, size=size)
    return {"suppliers": suppliers, "total": total, "page": page, "size": size}


@router.get("/assignable-users")
def assignable_users(db: Session = Depends(get_db)) -> dict:
    return {"users": [svc.user_brief(u) for u in svc.assignable_users(db)]}


@router.put("/{supplier_id}", dependencies=_MGR)
def set_assignees(supplier_id: int, payload: AssigneesPayload, db: Session = Depends(get_db)) -> dict:
    supplier = db.get(SupplierMaster, supplier_id)
    if supplier is None:
        raise HTTPException(404, "Supplier not found")
    ids = svc.set_assignees(db, supplier_id, payload.user_ids)
    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier.supplier_name,
        "assignees": svc.assignees_detail(db, ids),
    }
