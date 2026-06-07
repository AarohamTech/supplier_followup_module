from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class MailHistory(Base):
    __tablename__ = "mail_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    procurement_record_id: Mapped[int] = mapped_column(ForeignKey("procurement_records.id"), index=True, nullable=False)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier_master.id"), index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    supplier_po_no: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    material_name: Mapped[str] = mapped_column(String(500), nullable=False)
    to_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cc_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    bcc_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    escalation_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    subject: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text)
    mail_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sent_status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    remarks: Mapped[str | None] = mapped_column(Text)
