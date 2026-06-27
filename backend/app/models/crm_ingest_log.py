from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class CrmIngestLog(Base):
    """One row per CRM ingestion run — the admin-visible fetch history.

    Records how many POs were fetched / added (created) / changed (updated) /
    skipped / errored on each poll, plus timing and any error message.
    """

    __tablename__ = "crm_ingest_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # OK / ERROR / DISABLED
    trigger: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)  # auto / manual
    desk: Mapped[str | None] = mapped_column(String(16))
    fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
