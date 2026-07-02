"""Persistent HI-assistant chat messages, keyed by purchase-order ID."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class HiAgentChatMessage(Base):
    __tablename__ = "hi_agent_chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The procurement record ID is deliberately also the logical thread ID.
    # Keeping the explicit string makes the API contract clear and leaves room
    # for non-PO thread kinds later without changing the table shape.
    thread_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    procurement_record_id: Mapped[int] = mapped_column(
        ForeignKey("procurement_records.id"), index=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    actions: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

