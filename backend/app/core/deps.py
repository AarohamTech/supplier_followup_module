"""FastAPI auth dependencies — current user resolution + RBAC guards.

Usage:

    from ..core.deps import get_current_user, require_role
    from ..core.roles import Role

    @router.get("/secret")
    def secret(user = Depends(get_current_user)): ...          # any logged-in user

    @router.post("/danger", dependencies=[Depends(require_role(Role.MANAGER))])
    def danger(): ...                                          # manager or admin
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from . import roles as roles_mod
from .roles import Role
from .security import TokenError, decode_token

# auto_error=False → we raise our own 401 with a clean message.
_bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise _CREDENTIALS_EXC
    try:
        payload = decode_token(creds.credentials)
    except TokenError:
        raise _CREDENTIALS_EXC

    sub = payload.get("sub")
    if sub is None:
        raise _CREDENTIALS_EXC
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise _CREDENTIALS_EXC

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_staff(user: User = Depends(get_current_user)) -> User:
    """Any logged-in *staff* user (internal account). Rejects portal accounts.

    Use as the base dependency for internal `/api/*` business + AI routers so a
    supplier or employee portal account can never reach them — not even on GET.
    """
    if user.supplier_id is not None or user.emp_code is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal endpoint — not available to portal accounts",
        )
    return user


def get_current_supplier(user: User = Depends(get_current_user)) -> User:
    """The logged-in *supplier* user. Rejects staff accounts.

    Portal handlers derive their data scope from `user.supplier_id`.
    """
    if user.supplier_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supplier portal endpoint — requires a supplier account",
        )
    return user


def get_current_employee(user: User = Depends(get_current_user)) -> User:
    """The logged-in *employee* user. Rejects staff and supplier accounts.

    Employee portal handlers derive their data scope from `user.emp_code`
    (matched against ProcurementRecord.owner_emp_code).
    """
    if user.emp_code is None or user.supplier_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee portal endpoint — requires an employee account",
        )
    return user


def require_role(minimum: str):
    """Dependency factory: require `minimum` role or higher (hierarchical).

    Because roles are strictly ranked, `require_role(Role.ADMIN)` allows only
    admins, while `require_role(Role.MANAGER)` allows managers and admins.
    """

    def _guard(user: User = Depends(get_current_user)) -> User:
        if not roles_mod.role_at_least(user.role, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{minimum}' role or higher",
            )
        return user

    return _guard


# Convenience guards.
require_admin = require_role(Role.ADMIN)
require_manager = require_role(Role.MANAGER)   # manager + admin
require_writer = require_role(Role.USER)       # user + manager + admin (excludes viewer)


def require_writer_for_writes(
    request: Request, user: User = Depends(get_current_user)
) -> User:
    """Method-aware guard: reads (GET/HEAD/OPTIONS) are open to any logged-in
    user (viewer included); any state-changing method requires `user` or higher.

    Applied at the router level so a `viewer` is effectively read-only across the
    whole app, while send/approve-style endpoints add their own `require_manager`.

    Portal accounts are rejected outright (even on reads) — internal business
    routers are staff-only; suppliers use `/api/portal/*` and employees use
    `/api/eportal/*` instead.
    """
    if user.supplier_id is not None or user.emp_code is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal endpoint — not available to portal accounts",
        )
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return user
    if not roles_mod.role_at_least(user.role, Role.USER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read-only role — changes require 'user' or higher",
        )
    return user
