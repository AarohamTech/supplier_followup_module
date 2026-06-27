"""Authentication router: login, current user, self password change."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.deps import get_current_user
from ..core.security import create_access_token, verify_password
from ..database import get_db
from ..models.supplier import SupplierMaster
from ..models.user import User
from ..schemas.user import ChangePasswordRequest, LoginRequest, Token, UserOut
from ..services import user_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(db: Session, user: User) -> UserOut:
    """UserOut with `supplier_name` populated for supplier portal accounts."""
    out = UserOut.model_validate(user)
    if user.supplier_id is not None:
        supplier = db.get(SupplierMaster, user.supplier_id)
        if supplier is not None:
            out.supplier_name = supplier.supplier_name
    return out


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    if payload.username:
        user = user_service.authenticate_by_username(db, payload.username, payload.password)
    else:
        user = user_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(subject=user.id, role=user.role, email=user.email)
    return Token(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_out(db, user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return user_out(db, user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    # The user is setting their own password → clear any force-change flag
    # (e.g. a supplier completing the first-login change).
    user_service.set_password(db, user, payload.new_password, must_change=False)
    return {"ok": True}
