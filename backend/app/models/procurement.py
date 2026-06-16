from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ProcurementRecord(Base):
    """
    Latest procurement intake schema.

    Business unique key: crm_no + supplier_po_no + material_name.
    """

    __tablename__ = "procurement_records"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Latest Excel / ERP source fields.
    crm_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    material_name: Mapped[str] = mapped_column(String(500), nullable=False)
    uom: Mapped[str | None] = mapped_column(String(16))
    lead_time: Mapped[int | None] = mapped_column(Integer) 
    shipment_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    signal: Mapped[str | None] = mapped_column(String(16), index=True)
    stock: Mapped[float | None] = mapped_column(Numeric(18, 3))
    qty: Mapped[float | None] = mapped_column(Numeric(18, 3))
    po_status: Mapped[str | None] = mapped_column(String(32))
    adv_status: Mapped[str | None] = mapped_column(String(32))
    supplier_po_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    supplier_date: Mapped[date | None] = mapped_column(Date)
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    quantity: Mapped[float | None] = mapped_column("supplier_quantity", Numeric(18, 3))
    rate: Mapped[float | None] = mapped_column(Numeric(18, 4))

    # Deprecated source columns retained for old local SQLite databases only.
    crm_date: Mapped[date | None] = mapped_column(Date)
    mdn_no: Mapped[str | None] = mapped_column(String(64), index=True)
    mdn_date: Mapped[date | None] = mapped_column(Date)
    rate_given_date: Mapped[datetime | None] = mapped_column(DateTime)
    po_no: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    po_date: Mapped[date | None] = mapped_column(Date)
    po_validity: Mapped[date | None] = mapped_column(Date)
    customer_name: Mapped[str | None] = mapped_column(String(255), index=True)

    # System-generated fields.
    followup_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    mail_status: Mapped[str] = mapped_column(String(32), default="NOT_SENT")
    followup_count: Mapped[int] = mapped_column(Integer, default=0)
    last_followup_date: Mapped[datetime | None] = mapped_column(DateTime)
    last_supplier_reply: Mapped[str | None] = mapped_column(Text)
    commitment_date: Mapped[date | None] = mapped_column(Date)
    delay_reason: Mapped[str | None] = mapped_column(String(500))
    escalation_level: Mapped[str] = mapped_column(String(32), default="NONE")
    ai_required: Mapped[bool] = mapped_column(Boolean, default=False)
    next_followup_date: Mapped[datetime | None] = mapped_column(DateTime)
    # When the record first became RED — anchors the RED escalation day count
    # ("day 1" = first day late) instead of counting from the ship date.
    red_since: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("crm_no", "supplier_po_no", "material_name", name="uq_procurement_match_latest"),
        Index("ix_procurement_signal_status", "signal", "po_status"),
    )
