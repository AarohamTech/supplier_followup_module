from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


# Status / signal vocab
TASK_STATUSES = (
    "BACKLOG",
    "TODO",
    "IN_PROGRESS",
    "WAITING_SUPPLIER",
    "WAITING_CUSTOMER",
    "BLOCKED",
    "DONE",
)
TASK_PRIORITIES = ("P0", "P1", "P2", "P3")
TASK_SIGNALS = ("GREEN", "YELLOW", "RED", "BLACK")
TASK_SOURCES = ("SUPPLIER", "CUSTOMER", "INTERNAL", "ESCALATION")


class CommunicationTask(Base):
    """Lightweight task model that links suppliers / POs / mail threads to follow-up actions."""

    __tablename__ = "communication_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Linkage (all optional so users can create tasks at any granularity)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_master.id"), index=True
    )
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    supplier_po_no: Mapped[str | None] = mapped_column(String(64), index=True)
    procurement_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("procurement_records.id"), index=True
    )
    linked_mail_id: Mapped[int | None] = mapped_column(
        ForeignKey("mail_history.id"), index=True
    )
    customer_mail_id: Mapped[int | None] = mapped_column(Integer, index=True)
    material_name: Mapped[str | None] = mapped_column(String(500))
    task_source: Mapped[str] = mapped_column(String(16), default="SUPPLIER", index=True)
    created_from_mail_id: Mapped[int | None] = mapped_column(Integer, index=True)

    # Content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Assignment
    assigned_to: Mapped[str | None] = mapped_column(String(128), index=True)
    assigned_by: Mapped[str | None] = mapped_column(String(128))
    watchers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Workflow
    priority: Mapped[str] = mapped_column(String(8), default="P2", index=True)
    status: Mapped[str] = mapped_column(String(32), default="TODO", index=True)
    signal: Mapped[str] = mapped_column(String(16), default="YELLOW", index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timing
    due_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    reminder_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Counters (kept simple, denormalized for now)
    comments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
