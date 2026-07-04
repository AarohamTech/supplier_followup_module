"""Pydantic DTOs for auth + user management."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from ..core.roles import ALL_ROLES, DEFAULT_ROLE, normalize_role
from .company import CompanyBrief


def _validate_role(value: str | None) -> str | None:
    if value is None:
        return None
    norm = normalize_role(value)
    if norm not in ALL_ROLES:
        raise ValueError(f"role must be one of {ALL_ROLES}")
    return norm


# ── Output ───────────────────────────────────────────────────────────────────
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Plain str (not EmailStr): internal employee accounts use a synthetic
    # placeholder address and log in by username, not email.
    email: str
    # Login id for accounts without an email (internal employees).
    username: str | None = None
    full_name: str | None = None
    role: str
    is_active: bool
    # Supplier portal accounts carry a supplier_id (NULL → internal staff account).
    supplier_id: int | None = None
    # Employee portal accounts carry an emp_code (their CRM EmpCode).
    emp_code: str | None = None
    must_change_password: bool = False
    # Convenience field populated by the auth/portal routers (not an ORM column).
    supplier_name: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── Auth ─────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    # Staff/suppliers log in by email; internal employees by username.
    email: EmailStr | None = None
    username: str | None = None
    password: str = Field(min_length=1)
    # Company code chosen at login (staff only; portal accounts are pinned). When
    # omitted, the default company (102) is used.
    company: str | None = None

    @model_validator(mode="after")
    def _one_identifier(self) -> "LoginRequest":
        if not self.email and not self.username:
            raise ValueError("Provide email or username")
        return self


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut
    company: CompanyBrief | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


# ── Admin user management ────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    role: str = Field(default=DEFAULT_ROLE)

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        return _validate_role(v) or DEFAULT_ROLE


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _role(cls, v: str | None) -> str | None:
        return _validate_role(v)


class AdminResetPassword(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)
