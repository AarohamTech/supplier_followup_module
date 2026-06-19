"""Human feedback on AI outputs — the dataset that drives prompt/RAG tuning.

Each row captures one thumbs-up/down on a generated draft, ideally with the
human's edited/final version, so we can see exactly how people correct the AI
and later use it for few-shot prompting or fine-tuning.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Which AI surface: po_followup_command / customer_reply / assistant / triage / ...
    feature: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    rating: Mapped[str] = mapped_column(String(8), index=True, nullable=False)  # up | down

    instruction: Mapped[str | None] = mapped_column(Text)      # the user's command/prompt
    ai_output: Mapped[str | None] = mapped_column(Text)        # what the AI produced
    edited_output: Mapped[str | None] = mapped_column(Text)    # what the human changed it to
    context_ref: Mapped[str | None] = mapped_column(String(128), index=True)  # e.g. supplier_po_no
    note: Mapped[str | None] = mapped_column(Text)             # optional free-text reason
    user_email: Mapped[str | None] = mapped_column(String(255), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
