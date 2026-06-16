"""Admin user-management router. Every route requires the `admin` role."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_admin
from ..core.roles import ALL_ROLES
from ..database import get_db
from ..models.user import User
from ..schemas.user import AdminResetPassword, UserCreate, UserOut, UserUpdate
from ..services import user_service
from ..services.user_service import EmailTakenError, LastAdminError

# Router-level guard: admin only for the whole prefix.
router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
) -> list[User]:
    return user_service.list_users(db, role=role, is_active=is_active, search=search)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    try:
        return user_service.create_user(
            db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role=payload.role,
        )
    except EmailTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/meta/roles")
def role_options() -> dict:
    return {"roles": list(ALL_ROLES)}


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)) -> User:
    user = user_service.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> User:
    try:
        user = user_service.update_user(
            db,
            user_id,
            full_name=payload.full_name,
            role=payload.role,
            is_active=payload.is_active,
        )
    except LastAdminError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int, payload: AdminResetPassword, db: Session = Depends(get_db)
) -> dict:
    user = user_service.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user_service.set_password(db, user, payload.new_password)
    return {"ok": True, "user_id": user_id}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> dict:
    user = user_service.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    # Reuse the last-admin guard by deactivating through the service first.
    if user.role == "admin" and user_service.count_active_admins(db, exclude_id=user.id) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot delete the last active admin"
        )
    db.delete(user)
    db.commit()
    return {"ok": True, "deleted_id": user_id}
