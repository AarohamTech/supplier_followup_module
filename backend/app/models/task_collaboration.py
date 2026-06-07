"""Task collaboration models: threaded comments and an immutable activity log."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


TASK_ACTIVITY_TYPES = (
    "CREATED",
    "STATUS_CHANGED",
    "ASSIGNEE_CHANGED",
    "PRIORITY_CHANGED",
    "DUE_DATE_CHANGED",
    "COMMENT_ADDED",
    "ESCALATED",
)


class TaskComment(Base):
    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("communication_tasks.id"), index=True, nullable=False
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class TaskActivityLog(Base):
    __tablename__ = "task_activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("communication_tasks.id"), index=True, nullable=False
    )
    activity_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(500))
    new_value: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
