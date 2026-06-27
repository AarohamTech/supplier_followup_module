"""Audit log of PO follow-up attempts (auto + manual).

One row per attempt so the auto-followup loop is no longer a black box: it
records whether a follow-up was queued, skipped (and why), or failed, whether
Harmony Intelligent was used, and any AI/error detail — even when nothing was sent.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


# source of the attempt
ATTEMPT_SOURCES = ("auto", "manual", "command")
# outcome of the attempt
ATTEMPT_OUTCOMES = ("QUEUED", "SKIPPED", "FAILED")


class FollowupAttempt(Base):
    __tablename__ = "followup_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)

    supplier_po_no: Mapped[str | None] = mapped_column(String(64), index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    signal: Mapped[str | None] = mapped_column(String(16), index=True)
    mail_type: Mapped[str | None] = mapped_column(String(64))

    source: Mapped[str] = mapped_column(String(16), default="auto", index=True, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)  # skip reason / error message

    ai_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_error: Mapped[str | None] = mapped_column(Text)

    history_id: Mapped[int | None] = mapped_column(Integer, index=True)
    message_id: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, nullable=False
    )
