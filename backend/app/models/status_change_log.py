"""Audit log of procurement-record changes triggered by parsed supplier replies."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class StatusChangeLog(Base):
    __tablename__ = "status_change_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    procurement_record_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_records.id"), index=True, nullable=False
    )
    source_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("communication_messages.id"), index=True
    )

    old_status: Mapped[str | None] = mapped_column(String(64))
    new_status: Mapped[str | None] = mapped_column(String(64))
    old_shipment_date: Mapped[date | None] = mapped_column(Date)
    new_shipment_date: Mapped[date | None] = mapped_column(Date)
    old_qty: Mapped[float | None] = mapped_column()
    new_qty: Mapped[float | None] = mapped_column()

    action_taken: Mapped[str | None] = mapped_column(String(128), index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
