from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from ..database import Base


class SupplierEmail(Base):
    __tablename__ = "supplier_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier_master.id"), index=True, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    to_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cc_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    bcc_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    escalation_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
