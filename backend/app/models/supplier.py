from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class SupplierMaster(Base):
    __tablename__ = "supplier_master"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    latest_supplier_po_no: Mapped[str | None] = mapped_column(String(64), index=True)
    latest_signal: Mapped[str | None] = mapped_column(String(16), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
