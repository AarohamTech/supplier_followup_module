from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class SupplierEmailAudit(Base):
    """Append-only change log for supplier email mappings (who changed what).

    One row per CREATE / UPDATE / DELETE on `supplier_emails`. `changes` holds a
    field-keyed diff: {field: {"old": ..., "new": ...}}. Visible to admins only.
    Not a FK to `supplier_emails` — the row must survive a mapping's deletion.
    """

    __tablename__ = "supplier_email_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_email_id: Mapped[int | None] = mapped_column(Integer, index=True)
    supplier_id: Mapped[int | None] = mapped_column(Integer, index=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # CREATE/UPDATE/DELETE
    changed_by_id: Mapped[int | None] = mapped_column(Integer)
    changed_by: Mapped[str | None] = mapped_column(String(255))  # actor email/name
    changes: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, nullable=False
    )
