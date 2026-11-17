"""Per-employee feature permissions for the employee portal.

Each flag is a nullable Boolean column on `users`. Employees get every
permission by default: NULL (rows that predate the column) and True both mean
granted; only an explicit False (an admin switched it off on Employee Logins)
revokes it. Pure service layer: no FastAPI imports.
"""
from __future__ import annotations

from ..core.account_kind import is_employee_account
from ..models.user import User

SUPPLIER_ASSIGNMENTS = "can_manage_supplier_assignments"
EMAIL_MASTER = "can_manage_email_master"

ALL_PERMISSIONS: tuple[str, ...] = (SUPPLIER_ASSIGNMENTS, EMAIL_MASTER)


def has_permission(user: User | None, flag: str) -> bool:
    """True when `user` is an employee account holding `flag` (NULL = granted)."""
    if not is_employee_account(user):
        return False
    if flag not in ALL_PERMISSIONS:
        return False
    return getattr(user, flag, None) is not False


def permissions_of(user: User) -> dict[str, bool]:
    return {flag: has_permission(user, flag) for flag in ALL_PERMISSIONS}
