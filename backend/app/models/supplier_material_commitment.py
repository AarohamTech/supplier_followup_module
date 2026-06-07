"""Material-wise supplier commitments captured from parsed reply tables.

One row per (supplier_po_no, material_code or material_name). Newer replies
overwrite the latest commitment but the full history is preserved by inserting
new rows when the underlying procurement record id differs or by leaving
existing rows in place and writing an updated one.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


COMMITMENT_STATUSES = (
    "PENDING",
    "CONFIRMED",
    "DELAYED",
    "PARTIAL",
    "DISPATCHED",
    "CANCELLED",
    "ON_HOLD",
)


class SupplierMaterialCommitment(Base):
    __tablename__ = "supplier_material_commitments"

    id: Mapped[int] = mapped_column(primary_key=True)

    procurement_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("procurement_records.id"), index=True
    )
    reply_mail_id: Mapped[int | None] = mapped_column(
        ForeignKey("communication_messages.id"), index=True
    )

    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_master.id"), index=True
    )
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    supplier_po_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    material_code: Mapped[str | None] = mapped_column(String(128), index=True)
    material_name: Mapped[str] = mapped_column(String(500), nullable=False)

    commitment_qty: Mapped[float | None] = mapped_column(Numeric(18, 3))
    commitment_date: Mapped[date | None] = mapped_column(Date, index=True)
    supplier_status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    supplier_remark: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "supplier_po_no",
            "material_name",
            name="uq_commitment_po_material",
        ),
    )
