"""Engine job registry & per-run logs.

The engine job rows are the source of truth for cron toggles, intervals,
and run history. APScheduler reads from here on startup.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class EngineJob(Base):
    __tablename__ = "engine_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str | None] = mapped_column(String(32))
    last_message: Mapped[str | None] = mapped_column(Text)
    total_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EngineJobLog(Base):
    __tablename__ = "engine_job_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text)
