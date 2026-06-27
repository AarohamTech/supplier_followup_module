"""Application user with a role for RBAC.

Passwords are never stored in plaintext — only the bcrypt hash produced by
`core.security`. Role values come from `core.roles.ALL_ROLES`.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.roles import DEFAULT_ROLE
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Login identifier for accounts without an email (internal employees log in
    # with their CRM login id, e.g. "PRAMOD"). NULL for staff/supplier accounts,
    # who log in by email. Uniqueness is enforced in app code (schema-evolve only
    # adds columns, not constraints, to the live DB).
    username: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default=DEFAULT_ROLE, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # External supplier accounts link to a supplier_master row. NULL → internal
    # staff account (the 4-tier RBAC). Set → supplier portal account scoped to
    # that supplier's data. See core/roles.py (Role.SUPPLIER) and core/deps.py.
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_master.id"), index=True, nullable=True
    )
    # Internal employee accounts carry their CRM employee code (CRM `EmpCode`).
    # Set → employee portal account scoped to POs where owner_emp_code == this.
    # NULL → staff or supplier account. See core/roles.py (Role.EMPLOYEE).
    emp_code: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    # Forces a password change on next login (temp/admin-reset credentials).
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
