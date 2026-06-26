"""Per-user in-app notifications (staff + supplier accounts).

One row per recipient per event, so read state is tracked per user. Created by
`services/notification_service` when cross-party events happen (a supplier
messages their buyer, a buyer replies, an ASN is submitted/delivered, …).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    # Frontend route to open when the notification is clicked.
    link: Mapped[str | None] = mapped_column(String(255))

    # Optional context for grouping / deep-linking.
    supplier_id: Mapped[int | None] = mapped_column(Integer, index=True)
    supplier_po_no: Mapped[str | None] = mapped_column(String(64), index=True)
    procurement_record_id: Mapped[int | None] = mapped_column(Integer)
    asn_id: Mapped[int | None] = mapped_column(Integer)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, nullable=False
    )
