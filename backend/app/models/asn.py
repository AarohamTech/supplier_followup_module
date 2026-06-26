"""Advance Shipping Notice (ASN) — supplier-submitted shipment tracking.

A supplier raises an ASN against one of their POs, then advances it through a
shipment lifecycle (Draft → Dispatched → In Transit → At Customs → Inbound Hub →
Out for Delivery → Delivered). `AsnItem` holds the shipped line items;
`AsnEvent` is the per-leg tracking timeline.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Asn(Base):
    __tablename__ = "asns"

    id: Mapped[int] = mapped_column(primary_key=True)
    asn_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_master.id"), index=True, nullable=False
    )
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    supplier_po_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    crm_no: Mapped[str | None] = mapped_column(String(64))

    carrier_name: Mapped[str | None] = mapped_column(String(255))
    tracking_no: Mapped[str | None] = mapped_column(String(128), index=True)
    transport_mode: Mapped[str | None] = mapped_column(String(16))  # SEA/AIR/ROAD/RAIL
    origin: Mapped[str | None] = mapped_column(String(255))
    destination: Mapped[str | None] = mapped_column(String(255))

    dispatch_date: Mapped[datetime | None] = mapped_column(DateTime)
    eta: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Lifecycle stage; see services/asn_service.STAGE_META.
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True, nullable=False)
    status_label: Mapped[str | None] = mapped_column(String(64))
    alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_reason: Mapped[str | None] = mapped_column(String(255))
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)

    created_by_user_id: Mapped[int | None] = mapped_column(Integer)
    created_by_email: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[list["AsnItem"]] = relationship(
        back_populates="asn", cascade="all, delete-orphan", order_by="AsnItem.id"
    )
    events: Mapped[list["AsnEvent"]] = relationship(
        back_populates="asn", cascade="all, delete-orphan", order_by="AsnEvent.occurred_at"
    )


class AsnItem(Base):
    __tablename__ = "asn_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    asn_id: Mapped[int] = mapped_column(ForeignKey("asns.id"), index=True, nullable=False)
    procurement_record_id: Mapped[int | None] = mapped_column(Integer, index=True)
    material_name: Mapped[str] = mapped_column(String(500), nullable=False)
    material_code: Mapped[str | None] = mapped_column(String(64))
    # PO (ordered) quantity, captured for reference alongside what's being shipped.
    po_qty: Mapped[float | None] = mapped_column(Numeric(18, 3))
    qty_shipped: Mapped[float | None] = mapped_column(Numeric(18, 3))
    uom: Mapped[str | None] = mapped_column(String(16))
    invoice_no: Mapped[str | None] = mapped_column(String(64))

    asn: Mapped["Asn"] = relationship(back_populates="items")


class AsnEvent(Base):
    __tablename__ = "asn_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    asn_id: Mapped[int] = mapped_column(ForeignKey("asns.id"), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    status_label: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255))

    asn: Mapped["Asn"] = relationship(back_populates="events")
