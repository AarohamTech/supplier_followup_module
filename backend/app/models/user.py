"""Application user with a role for RBAC.

Passwords are never stored in plaintext — only the bcrypt hash produced by
`core.security`. Role values come from `core.roles.ALL_ROLES`.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.roles import DEFAULT_ROLE
from ..database import Base


class User(Base):
    __tablename__ = "users"
    # Email is unique per company, not globally: a supplier contact who deals
    # with both companies (e.g. SHIVAM ENGINEERS in 101 and 102) needs a portal
    # login in each, and each login is pinned to its own company. Staff accounts
    # (company_id NULL) stay unique among themselves. The live DB's old global
    # unique index is swapped for this one at startup
    # (schema_evolve.relax_users_email_unique). The index is declared below the
    # class because it is built from the mapped columns.

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
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
    # Deliberately NOT a foreign key: `users` is shared in `public`, while each
    # company keeps its own supplier_master — the id is only meaningful inside
    # the company in `company_id`. An FK to public.supplier_master made every
    # company-101 supplier login fail (see schema_evolve.drop_cross_company_fks).
    supplier_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    # Internal employee accounts carry their CRM employee code (CRM `EmpCode`).
    # Set → employee portal account scoped to POs where owner_emp_code == this.
    # NULL → staff or supplier account. See core/roles.py (Role.EMPLOYEE).
    emp_code: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    # Company (tenant) this account is pinned to. NULL → staff account resolved to
    # the default company (102). Set → portal account scoped to that company only.
    # Both `users` and `companies` live in `public`, so this FK is same-schema.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), index=True, nullable=True
    )
    # Forces a password change on next login (temp/admin-reset credentials).
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Employee-portal permissions (only meaningful when emp_code is set). Granted
    # by default; an admin can switch them off per employee on Employee Logins.
    # Nullable on purpose: rows that predate the column read NULL, and NULL means
    # granted (see services/employee_permissions.py).
    can_manage_supplier_assignments: Mapped[bool | None] = mapped_column(
        Boolean, default=True, nullable=True
    )
    can_manage_email_master: Mapped[bool | None] = mapped_column(
        Boolean, default=True, nullable=True
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# Per-company email uniqueness (see the note on the class). NULL company_id
# (staff, legacy default-company logins) folds to 0.
Index(
    "uq_users_email_company",
    func.lower(User.email),
    func.coalesce(User.company_id, 0),
    unique=True,
)
