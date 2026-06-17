"""Customer / general mail inbox.

Rows are created when an incoming mail does not match a known supplier mapping,
so the operations team can triage and assign these mails separately from the
supplier follow-up flow.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


CUSTOMER_MAIL_TYPES = (
    "GENERAL",
    "CUSTOMER",
    "INTERNAL",
    "SUPPLIER",
    "COMPLAINT",
    "DISPATCH",
    "QUALITY",
    "FINANCE",
)
CUSTOMER_MAIL_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED")
CUSTOMER_MAIL_PRIORITIES = ("P0", "P1", "P2", "P3")


class CustomerMail(Base):
    __tablename__ = "customer_mails"

    id: Mapped[int] = mapped_column(primary_key=True)

    from_email: Mapped[str | None] = mapped_column(String(255), index=True)
    from_name: Mapped[str | None] = mapped_column(String(255))
    to_email: Mapped[str | None] = mapped_column(String(255))
    cc_email: Mapped[str | None] = mapped_column(String(500))
    subject: Mapped[str | None] = mapped_column(String(500), index=True)
    body: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    mail_type: Mapped[str] = mapped_column(String(32), default="GENERAL", index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(128), index=True)
    priority: Mapped[str] = mapped_column(String(8), default="P2")

    linked_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("communication_tasks.id"), index=True
    )
    linked_supplier_po_no: Mapped[str | None] = mapped_column(String(64), index=True)

    attachments_json: Mapped[list | None] = mapped_column(JSON, default=list)
    message_uid: Mapped[str | None] = mapped_column(String(255), index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)

    # ── AI triage (populated on fetch or on demand; all nullable) ────────────
    # Category mirrors mail_type vocab but is the model's classification.
    ai_category: Mapped[str | None] = mapped_column(String(32), index=True)
    # Urgency the team should treat this with: HIGH / MEDIUM / LOW.
    ai_urgency: Mapped[str | None] = mapped_column(String(16), index=True)
    # Suggested next action: REPLY / ESCALATE / RESOLVE / MONITOR.
    ai_action: Mapped[str | None] = mapped_column(String(32))
    # One-line AI summary of the mail (and thread, when summarized).
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_triaged_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
