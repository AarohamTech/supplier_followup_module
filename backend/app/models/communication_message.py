"""Central message store for the Communication Hub.

Holds BOTH incoming supplier replies (fetched via IMAP / webhook) and
outgoing system mails (drafts, ready-to-send, sent). Replaces the role of
`mail_history` going forward; `mail_history` is kept for backward compatibility
during migration.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


# Vocab
MESSAGE_DIRECTIONS = ("INCOMING", "OUTGOING")
MESSAGE_CHANNELS = ("EMAIL",)
MESSAGE_STATUSES = (
    "RECEIVED",     # incoming, parsed or unparsed
    "DRAFT",        # outgoing, being composed
    "READY",        # outgoing, queued for send
    "SENT",         # outgoing, successfully sent
    "FAILED",       # outgoing, send failed
    "COPIED",       # outgoing, copied to clipboard (manual flow)
    "MAILTO_OPENED",  # outgoing, opened in user's mail client (manual flow)
    "SENT_MANUALLY",  # outgoing, user marked as sent manually
)


class CommunicationMessage(Base):
    __tablename__ = "communication_messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Linkage (all nullable so unmatched supplier replies can still be stored)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_master.id"), index=True
    )
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    procurement_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("procurement_records.id"), index=True
    )
    supplier_po_no: Mapped[str | None] = mapped_column(String(64), index=True)

    # Origin metadata
    direction: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default="EMAIL", nullable=False)
    mail_type: Mapped[str | None] = mapped_column(String(64), index=True)

    # Envelope
    subject: Mapped[str | None] = mapped_column(String(500), index=True)
    body: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    sender_email: Mapped[str | None] = mapped_column(String(255), index=True)
    receiver_email: Mapped[str | None] = mapped_column(String(255), index=True)
    to_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cc_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    bcc_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Workflow
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)

    # Provider linkage (for IMAP de-dup)
    message_uid: Mapped[str | None] = mapped_column(String(255), index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(255), index=True)

    # Parsed result (denormalized for fast filtering / display)
    parsed_status: Mapped[str | None] = mapped_column(String(64), index=True)
    parsed_qty: Mapped[float | None] = mapped_column()
    parsed_date: Mapped[datetime | None] = mapped_column(DateTime)
    parsed_payload: Mapped[dict | None] = mapped_column(JSON)

    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    received_at: Mapped[datetime | None] = mapped_column(DateTime)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
