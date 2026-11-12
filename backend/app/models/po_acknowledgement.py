"""Supplier acknowledgement of a purchase order.

One row per (supplier, vendor PO). A supplier acknowledges a PO by clicking the
signed "Acknowledge PO" link in a follow-up mail (`via='link'`) or the button on
the supplier portal PO page (`via='portal'`). The first acknowledgement wins;
later clicks only read it back.

The PO key is the supplier-facing vendor PO reference (`po_short_ref`) when the
feed gave one, else the recycled CRM counter (`supplier_po_no`) — the same
identity the Communication Hub threads by. Per-company table.

Acknowledging is NOT a dispatch commitment: follow-up suppression ignores it.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PoAcknowledgement(Base):
    __tablename__ = "po_acknowledgements"
    __table_args__ = (
        UniqueConstraint("supplier_key", "po_key", name="uq_po_ack_supplier_po"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Upper-cased, trimmed supplier name — the lookup key (names are matched
    # case-insensitively everywhere else in the app).
    supplier_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    supplier_po_no: Mapped[str | None] = mapped_column(String(64), index=True)
    po_short_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    # po_short_ref when known, else supplier_po_no.
    po_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    procurement_record_id: Mapped[int | None] = mapped_column(Integer)

    acknowledged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    via: Mapped[str] = mapped_column(String(16), nullable=False)  # 'link' | 'portal'
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    # Supplier portal user who clicked (portal acks only; soft ref to users).
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
