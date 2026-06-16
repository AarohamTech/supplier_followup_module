"""Pydantic DTOs for auth + user management."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..core.roles import ALL_ROLES, DEFAULT_ROLE, normalize_role


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
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ── Auth ─────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut


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
