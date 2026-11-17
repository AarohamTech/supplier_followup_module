"""Which kind of account a `User` row is: supplier, employee portal, or staff.

- Supplier portal: `supplier_id` is set.
- Employee portal: `emp_code` is set AND the role is not a staff role
  (normally `role="employee"`).
- Staff: everything else. An employee login that an admin promotes to a staff
  role (viewer/user/manager/admin) on the Users page becomes staff at that level.
  It keeps its `emp_code`, so desk-owner data still links to it.

Duck-typed (no model import) so it can be used from deps, services and queries.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_

from .roles import ALL_ROLES


def is_supplier_account(user: Any) -> bool:
    return user is not None and user.supplier_id is not None


def is_employee_account(user: Any) -> bool:
    return (
        user is not None
        and user.supplier_id is None
        and user.emp_code is not None
        and user.role not in ALL_ROLES
    )


def is_staff_account(user: Any) -> bool:
    return user is not None and user.supplier_id is None and not is_employee_account(user)


def staff_clause(user_model: Any):
    """SQL filter matching staff accounts (mirror of `is_staff_account`)."""
    return and_(
        user_model.supplier_id.is_(None),
        or_(user_model.emp_code.is_(None), user_model.role.in_(ALL_ROLES)),
    )
