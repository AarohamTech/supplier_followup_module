"""Admin management of supplier portal logins. Every route requires `admin`.

Supplier logins are `User` rows with `role="supplier"` and a `supplier_id`. They
are provisioned from Email Master mappings (see services/supplier_account_service);
this router lets an admin review them and reset passwords / toggle access.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.deps import require_admin
from ..database import get_db
from ..models.user import User
from ..schemas.user import UserOut
from ..services import supplier_account_service as svc

router = APIRouter(
    prefix="/api/supplier-accounts",
    tags=["supplier-accounts"],
    dependencies=[Depends(require_admin)],
)


def _load_supplier_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.supplier_id is None:
        raise HTTPException(status_code=404, detail="Supplier login not found")
    return user


@router.get("", response_model=list[UserOut])
def list_logins(
    db: Session = Depends(get_db),
    supplier_id: int | None = Query(default=None),
) -> list[User]:
    if supplier_id is not None:
        return svc.list_supplier_logins(db, supplier_id)
    from sqlalchemy import select

    return list(
        db.scalars(
            select(User).where(User.supplier_id.is_not(None)).order_by(User.email)
        ).all()
    )


@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, db: Session = Depends(get_db)) -> dict:
    user = _load_supplier_user(db, user_id)
    result = svc.reset_supplier_login_password(db, user)
    return {"ok": True, **result}


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate(user_id: int, db: Session = Depends(get_db)) -> User:
    user = _load_supplier_user(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/activate", response_model=UserOut)
def activate(user_id: int, db: Session = Depends(get_db)) -> User:
    user = _load_supplier_user(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user
