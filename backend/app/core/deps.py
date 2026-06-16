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

from fastapi import Depends, HTTPException, status
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
