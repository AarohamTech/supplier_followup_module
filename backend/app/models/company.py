"""Company (tenant) registry — shared table in `public`.

One row per company. Maps a stable `code` (used in the JWT `company` claim) to the
Postgres `schema_name` that holds that company's business data, plus branding/theme
the frontend applies.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable business identifier embedded in the JWT `company` claim (e.g. "101").
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Postgres schema holding this company's business data. "public" for 102.
    schema_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    # Frontend theme key ("red" = current Hariom palette, "blue" = Enterprise).
    theme: Mapped[str] = mapped_column(String(32), default="red", nullable=False)
    brand_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Exactly one row should be the default (resolves a request with no company).
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
