"""Supplier -> app-user assignment (many-to-many).

Maps a supplier to the people responsible for it, so a supplier's incoming email
is routed (assigned + notified) to those users. Per-company table (suppliers are
per-company); ``user_id`` is a soft reference to the shared ``users`` table.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class SupplierAssignment(Base):
    __tablename__ = "supplier_assignment"
    __table_args__ = (
        UniqueConstraint("supplier_id", "user_id", name="uq_supplier_assignment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_master.id"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
