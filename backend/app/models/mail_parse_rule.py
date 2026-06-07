"""Database-driven regex rules used by mail_parser_service."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


# Fields a rule can extract from an inbound mail.
PARSE_FIELDS = (
    "supplier_po_no",
    "status",
    "expected_dispatch_date",
    "quantity",
    "remarks",
)

# Where the regex is applied.
PARSE_SOURCES = ("subject", "body", "subject_or_body")


class MailParseRule(Base):
    __tablename__ = "mail_parse_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    # Optional scope; null = global rule applied to all suppliers.
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_master.id"), index=True
    )

    regex_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="subject_or_body", nullable=False)

    # Priority: lower number applied first.
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
