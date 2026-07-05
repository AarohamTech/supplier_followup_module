"""Engine-level orchestration: SMTP/IMAP test, restart, consolidated health."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import SessionLocal
from ..models.communication_message import CommunicationMessage
from ..models.engine_job import EngineJob, EngineJobLog
from ..scheduler import (
    apply_scheduler_settings,
    get_scheduler,
    register_all_specs,
    restart_scheduler as _restart_scheduler,
    start_scheduler,
    stop_scheduler,
)
from ..services import engine_registry
from ..workers import mail_fetch_worker, mail_send_worker

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Config snapshots (passwords masked)
# ─────────────────────────────────────────────────────────────────────────────
def _mask(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def smtp_snapshot() -> dict[str, Any]:
    return {
        "enabled": bool(getattr(settings, "SMTP_ENABLED", False)),
        "host": settings.SMTP_HOST,
        "port": int(settings.SMTP_PORT or 0),
        "user": settings.SMTP_USER,
        "password_masked": _mask(settings.SMTP_PASSWORD),
        "from": settings.SMTP_FROM,
    }


def imap_snapshot() -> dict[str, Any]:
    return {
        "enabled": bool(getattr(settings, "MAIL_INBOX_ENABLED", False)),
        "protocol": settings.MAIL_FETCH_PROTOCOL,
        "use_ssl": bool(settings.MAIL_INBOX_USE_SSL),
        "host": settings.IMAP_HOST,
        "port": int(settings.IMAP_PORT or 0),
        "user": settings.IMAP_USER,
        "password_masked": _mask(settings.IMAP_PASSWORD),
        "folder": settings.IMAP_FOLDER,
    }


def mail_engine_snapshot() -> dict[str, Any]:
    return {
        "smtp": smtp_snapshot(),
        "imap": imap_snapshot(),
        "auto_po_followup_enabled": bool(getattr(settings, "AUTO_PO_FOLLOWUP_ENABLED", False)),
        "scheduler_enabled": bool(getattr(settings, "SCHEDULER_ENABLED", False)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Live tests
# ─────────────────────────────────────────────────────────────────────────────
def test_smtp() -> dict[str, Any]:
    result = mail_send_worker.test_smtp_connection()
    # If SMTP just came online, immediately drain any READY messages so the
    # user doesn't have to wait for the next scheduler tick.
    if result.get("ok"):
        try:
            drain = mail_send_worker.send_ready_messages(limit=50)
            result["drained"] = {
                "attempted": drain.get("attempted", 0),
                "results": drain.get("results", []),
            }
        except Exception as exc:  # noqa: BLE001
            result["drain_error"] = str(exc)
    return result


def test_imap() -> dict[str, Any]:
    return mail_fetch_worker.test_inbox_connection()


# ─────────────────────────────────────────────────────────────────────────────
# Engine lifecycle
# ─────────────────────────────────────────────────────────────────────────────
def start_engine() -> dict[str, Any]:
    register_all_specs()
    sched = start_scheduler()
    # Drain any pending outbox once the engine has just been started so the
    # user gets immediate feedback that mails are flowing.
    try:
        mail_send_worker.send_ready_messages(limit=50)
    except Exception:  # noqa: BLE001
        log.exception("Initial outbox drain after start_engine failed")
    return {
        "ok": sched is not None,
        "running": sched is not None,
        "jobs": [j.id for j in sched.get_jobs()] if sched else [],
    }


def stop_engine() -> dict[str, Any]:
    stop_scheduler()
    return {"ok": True, "running": False, "stopped_at": datetime.utcnow().isoformat()}


def restart_engine() -> dict[str, Any]:
    register_all_specs()
    result = _restart_scheduler()
    try:
        mail_send_worker.send_ready_messages(limit=50)
    except Exception:  # noqa: BLE001
        log.exception("Initial outbox drain after restart_engine failed")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Consolidated health
# ─────────────────────────────────────────────────────────────────────────────
def engine_health() -> dict[str, Any]:
    smtp = test_smtp()
    imap = test_imap()
    sched = get_scheduler()

    db: Session = SessionLocal()
    try:
        pending = db.scalar(
            select(func.count(CommunicationMessage.id)).where(
                CommunicationMessage.direction == "OUTGOING",
                CommunicationMessage.status == "READY",
            )
        ) or 0
        failed = db.scalar(
            select(func.count(CommunicationMessage.id)).where(
                CommunicationMessage.direction == "OUTGOING",
                CommunicationMessage.status == "FAILED",
            )
        ) or 0
        sent_today = db.scalar(
            select(func.count(CommunicationMessage.id)).where(
                CommunicationMessage.direction == "OUTGOING",
                CommunicationMessage.status == "SENT",
                func.date(CommunicationMessage.sent_at) == func.date(func.now()),
            )
        ) or 0
        last_error_log = db.scalars(
            select(EngineJobLog)
            .where(EngineJobLog.status == "ERROR")
            .order_by(EngineJobLog.id.desc())
            .limit(1)
        ).first()
        engine_jobs = list(db.scalars(select(EngineJob).order_by(EngineJob.id.asc())).all())
    finally:
        db.close()

    return {
        "ok": bool(smtp.get("ok")) and bool(imap.get("ok")) and sched is not None,
        "scheduler_running": sched is not None,
        "smtp": smtp,
        "imap": imap,
        "queue": {
            "pending_outbox": int(pending),
            "failed_outbox": int(failed),
            "sent_today": int(sent_today),
        },
        "last_error": {
            "job_name": last_error_log.job_name if last_error_log else None,
            "at": last_error_log.started_at.isoformat() if last_error_log else None,
            "message": last_error_log.error_detail or last_error_log.message
            if last_error_log
            else None,
        },
        "jobs": [
            {
                "job_name": j.job_name,
                "enabled": j.enabled,
                "interval_minutes": j.interval_minutes,
                "last_status": j.last_status,
                "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
                "total_runs": j.total_runs,
                "failed_runs": j.failed_runs,
            }
            for j in engine_jobs
        ],
        "checked_at": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cron-job admin helpers
# ─────────────────────────────────────────────────────────────────────────────
def list_cron_jobs(db: Session) -> list[dict[str, Any]]:
    rows = engine_registry.list_jobs(db)
    return [
        {
            "job_name": row.job_name,
            "display_name": row.display_name,
            "description": row.description,
            "enabled": row.enabled,
            "interval_minutes": row.interval_minutes,
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
            "last_status": row.last_status,
            "last_message": row.last_message,
            "total_runs": row.total_runs,
            "failed_runs": row.failed_runs,
        }
        for row in rows
    ]


def update_cron_job(
    db: Session,
    job_name: str,
    *,
    enabled: bool | None,
    interval_minutes: int | None,
) -> dict[str, Any] | None:
    row = engine_registry.update_job(
        db,
        job_name,
        enabled=enabled,
        interval_minutes=interval_minutes,
    )
    if row is None:
        return None
    apply_scheduler_settings()
    return {
        "job_name": row.job_name,
        "enabled": row.enabled,
        "interval_minutes": row.interval_minutes,
    }


def run_cron_job_now(job_name: str) -> dict[str, Any]:
    return engine_registry.run_job(job_name, manual=True)


def run_all_jobs(db: Session) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for row in engine_registry.list_jobs(db):
        if not row.enabled:
            continue
        results.append(engine_registry.run_job(row.job_name, manual=True))
    return {
        "ran": len(results),
        "results": results,
    }


def recent_job_logs(
    db: Session,
    *,
    job_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = engine_registry.recent_logs(db, job_name=job_name, limit=limit)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "job_name": row.job_name,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "status": row.status,
                "message": row.message,
                "records_processed": row.records_processed,
                "records_success": row.records_success,
                "records_failed": row.records_failed,
                "error_detail": row.error_detail,
            }
        )
    return out
