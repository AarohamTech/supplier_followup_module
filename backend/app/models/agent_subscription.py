"""Standing HI-agent subscriptions: per-thread followups and scheduled summaries.

Created PENDING by the agent (never sent on its own), confirmed to ACTIVE by a
human, then dispatched by the `agent_dispatch_cron` background job.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

SUBSCRIPTION_KINDS = ("FOLLOWUP", "SCHEDULED_SUMMARY")
SUBSCRIPTION_STATUSES = ("PENDING", "ACTIVE", "PAUSED", "CANCELLED")
SUMMARY_SCHEDULES = ("daily", "weekly")


class AgentSubscription(Base):
    __tablename__ = "agent_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)

    # Thread scope
    supplier_id: Mapped[int | None] = mapped_column(Integer, index=True)
    procurement_record_id: Mapped[int | None] = mapped_column(Integer, index=True)
    supplier_po_no: Mapped[str | None] = mapped_column(String(64), index=True)

    # Recipient (internal users only for subscriptions)
    recipient_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    recipient_label: Mapped[str | None] = mapped_column(String(255))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True, nullable=False)

    # FOLLOWUP high-water mark (CommunicationMessage.id already forwarded)
    last_forwarded_message_id: Mapped[int | None] = mapped_column(Integer, default=0)

    # SCHEDULED_SUMMARY scheduling
    schedule: Mapped[str | None] = mapped_column(String(32))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
