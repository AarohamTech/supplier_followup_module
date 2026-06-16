"""APScheduler wiring driven by the engine job registry.

Each cron job is registered in `services.engine_registry` and run through the
registry's wrapper, which records start/finish state into `engine_jobs` and
`engine_job_logs`. The scheduler loop simply picks up enabled jobs from the
registry and applies their interval from the matching `engine_jobs` row.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..database import SessionLocal
from ..models.communication_message import CommunicationMessage
from ..models.engine_job import EngineJob
from ..models.status_change_log import StatusChangeLog
from ..services import engine_registry, po_followup_mail_service, settings_service
from ..services.engine_registry import EngineJobSpec
from ..workers import mail_fetch_worker, mail_send_worker

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Job bodies (called by the registry wrapper)
# ─────────────────────────────────────────────────────────────────────────────
def mail_fetch_runner() -> dict[str, Any]:
    log.info("[cron] mail_fetch_runner starting")
    result = mail_fetch_worker.fetch_supplier_mails()
    log.info("[cron] mail_fetch_runner done: %s", result)
    return result


def status_change_runner() -> dict[str, Any]:
    db: Session = SessionLocal()
    try:
        latest = db.scalar(
            select(StatusChangeLog).order_by(StatusChangeLog.created_at.desc())
        )
        log.info("[cron] status_change_runner tick at %s", datetime.utcnow().isoformat())
        return {
            "ran_at": datetime.utcnow().isoformat(),
            "latest_log_present": bool(latest),
        }
    finally:
        db.close()


def auto_reply_runner() -> dict[str, Any]:
    db: Session = SessionLocal()
    created = 0
    try:
        candidates = db.scalars(
            select(CommunicationMessage)
            .where(
                CommunicationMessage.direction == "INCOMING",
                CommunicationMessage.status == "RECEIVED",
                CommunicationMessage.parsed_status.isnot(None),
                CommunicationMessage.procurement_record_id.isnot(None),
            )
            .order_by(CommunicationMessage.created_at.asc())
            .limit(25)
        ).all()

        for src in candidates:
            already = db.scalar(
                select(CommunicationMessage).where(
                    CommunicationMessage.in_reply_to == (src.message_uid or ""),
                    CommunicationMessage.direction == "OUTGOING",
                )
            )
            if already or not src.sender_email:
                continue
            subject = f"Re: {src.subject or 'Your update'}"
            body = (
                f"Thanks for the update on PO {src.supplier_po_no or ''}. "
                f"Noted status: {src.parsed_status}. "
                "We will revert if anything further is needed."
            )
            ack = CommunicationMessage(
                direction="OUTGOING",
                # DRAFT, not READY: auto-acknowledgements must be reviewed and
                # approved by a human before the send worker picks them up.
                status="DRAFT",
                channel="EMAIL",
                supplier_id=src.supplier_id,
                supplier_name=src.supplier_name,
                procurement_record_id=src.procurement_record_id,
                supplier_po_no=src.supplier_po_no,
                subject=subject,
                body=body,
                receiver_email=src.sender_email,
                to_emails=[src.sender_email],
                mail_type="AUTO_ACK",
                in_reply_to=src.message_uid,
            )
            db.add(ack)
            created += 1
        db.commit()
        return {
            "ran_at": datetime.utcnow().isoformat(),
            "drafts_created": created,
            "queued": created,
        }
    except Exception:  # noqa: BLE001
        log.exception("auto_reply_runner failed")
        db.rollback()
        return {
            "ran_at": datetime.utcnow().isoformat(),
            "drafts_created": created,
            "error": True,
        }
    finally:
        db.close()


def mail_send_runner() -> dict[str, Any]:
    log.info("[cron] mail_send_runner starting")
    result = mail_send_worker.send_ready_messages()
    log.info("[cron] mail_send_runner done: %s", result)
    return result


def po_followup_mail_runner() -> dict[str, Any]:
    log.info("[cron] po_followup_mail_runner starting")
    db: Session = SessionLocal()
    try:
        result = po_followup_mail_service.queue_due_po_followups(db)
        log.info("[cron] po_followup_mail_runner done: %s", result)
        return result
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("po_followup_mail_runner failed")
        return {"enabled": True, "queued": 0, "skipped": 0, "error": True}
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Registry bootstrapping
# ─────────────────────────────────────────────────────────────────────────────
JOB_SPECS: list[EngineJobSpec] = [
    EngineJobSpec(
        job_name="mail_fetch_cron",
        display_name="Mail Inbox Fetch",
        description="Fetch supplier replies via IMAP/POP3 and parse them.",
        default_interval_minutes=int(getattr(settings, "MAIL_FETCH_INTERVAL_MINUTES", 5) or 5),
        runner=mail_fetch_runner,
        category="MAIL",
    ),
    EngineJobSpec(
        job_name="status_change_cron",
        display_name="Status Change Scan",
        description="Surface counts of recent status reconciliations.",
        default_interval_minutes=int(getattr(settings, "STATUS_CHANGE_INTERVAL_MINUTES", 15) or 15),
        runner=status_change_runner,
        category="STATUS",
    ),
    EngineJobSpec(
        job_name="auto_reply_cron",
        display_name="Auto Reply Drafts",
        description="Create acknowledgement drafts for parsed supplier replies.",
        default_interval_minutes=int(getattr(settings, "AUTO_REPLY_INTERVAL_MINUTES", 15) or 15),
        runner=auto_reply_runner,
        category="MAIL",
    ),
    EngineJobSpec(
        job_name="po_followup_mail_cron",
        display_name="PO Follow-up Generator",
        description="Queue signal-based PO follow-up mails for due groups.",
        default_interval_minutes=int(getattr(settings, "MAIL_SEND_INTERVAL_MINUTES", 5) or 5),
        runner=po_followup_mail_runner,
        category="FOLLOWUP",
    ),
    EngineJobSpec(
        job_name="mail_send_cron",
        display_name="Mail Send Worker",
        description="Send queued OUTGOING/READY messages over SMTP.",
        default_interval_minutes=int(getattr(settings, "MAIL_SEND_INTERVAL_MINUTES", 5) or 5),
        runner=mail_send_runner,
        category="MAIL",
    ),
]


def register_all_specs() -> None:
    for spec in JOB_SPECS:
        engine_registry.register(spec)


def _ensure_db_rows() -> dict[str, EngineJob]:
    register_all_specs()
    db: Session = SessionLocal()
    try:
        engine_registry.ensure_job_rows(db)
        rows = engine_registry.list_jobs(db)
        return {row.job_name: row for row in rows}
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Wrappers used by APScheduler — record runs into the registry
# ─────────────────────────────────────────────────────────────────────────────
def _wrap(job_name: str):
    def _runner():
        return engine_registry.run_job(job_name)

    return _runner


# Public job entry points (preserved for legacy imports/tests)
def mail_fetch_cron() -> dict[str, Any]:
    return engine_registry.run_job("mail_fetch_cron")


def status_change_cron() -> dict[str, Any]:
    return engine_registry.run_job("status_change_cron")


def auto_reply_cron() -> dict[str, Any]:
    return engine_registry.run_job("auto_reply_cron")


def mail_send_cron() -> dict[str, Any]:
    return engine_registry.run_job("mail_send_cron")


def po_followup_mail_cron() -> dict[str, Any]:
    return engine_registry.run_job("po_followup_mail_cron")


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────
def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def _resolve_intervals() -> dict[str, int]:
    """Effective interval per job: EngineJob row → settings_service → env."""
    rows = _ensure_db_rows()
    db: Session = SessionLocal()
    try:
        env_intervals = settings_service.get_scheduler_intervals(db)
    except Exception:  # noqa: BLE001
        env_intervals = {}
    finally:
        db.close()

    legacy_map = {
        "mail_fetch_cron": "MAIL_FETCH_INTERVAL_MINUTES",
        "status_change_cron": "STATUS_CHANGE_INTERVAL_MINUTES",
        "auto_reply_cron": "AUTO_REPLY_INTERVAL_MINUTES",
        "mail_send_cron": "MAIL_SEND_INTERVAL_MINUTES",
        "po_followup_mail_cron": "MAIL_SEND_INTERVAL_MINUTES",
    }

    resolved: dict[str, int] = {}
    for spec in JOB_SPECS:
        row = rows.get(spec.job_name)
        if row is not None and row.interval_minutes:
            resolved[spec.job_name] = max(1, int(row.interval_minutes))
            continue
        env_key = legacy_map.get(spec.job_name)
        if env_key and env_key in env_intervals:
            resolved[spec.job_name] = max(1, int(env_intervals[env_key]))
            continue
        resolved[spec.job_name] = max(1, int(spec.default_interval_minutes))
    return resolved


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    register_all_specs()
    if not getattr(settings, "SCHEDULER_ENABLED", False):
        log.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        try:
            _ensure_db_rows()
        except Exception:  # noqa: BLE001
            log.exception("Failed to ensure engine_jobs rows while scheduler disabled")
        return None
    if _scheduler is not None:
        return _scheduler

    rows = _ensure_db_rows()
    intervals = _resolve_intervals()

    sched = BackgroundScheduler(timezone="UTC")
    for spec in JOB_SPECS:
        row = rows.get(spec.job_name)
        if row is not None and not row.enabled:
            log.info("Engine job %s is disabled — skipping schedule", spec.job_name)
            continue
        minutes = intervals.get(spec.job_name, spec.default_interval_minutes)
        sched.add_job(
            _wrap(spec.job_name),
            "interval",
            minutes=minutes,
            id=spec.job_name,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    sched.start()
    _scheduler = sched
    log.info("APScheduler started with %s jobs", len(sched.get_jobs()))
    return sched


def apply_scheduler_settings() -> dict[str, int]:
    """Reschedule running jobs to reflect updated interval / enabled toggles."""
    register_all_specs()
    rows = _ensure_db_rows()
    intervals = _resolve_intervals()

    sched = _scheduler
    if sched is None:
        return intervals

    for spec in JOB_SPECS:
        row = rows.get(spec.job_name)
        try:
            existing = sched.get_job(spec.job_name)
        except Exception:  # noqa: BLE001
            existing = None

        if row is not None and not row.enabled:
            if existing is not None:
                try:
                    sched.remove_job(spec.job_name)
                except Exception:  # noqa: BLE001
                    log.exception("Failed to remove disabled job %s", spec.job_name)
            continue

        minutes = intervals.get(spec.job_name, spec.default_interval_minutes)
        if existing is None:
            try:
                sched.add_job(
                    _wrap(spec.job_name),
                    "interval",
                    minutes=minutes,
                    id=spec.job_name,
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                )
            except Exception:  # noqa: BLE001
                log.exception("Failed to add job %s", spec.job_name)
            continue

        try:
            sched.reschedule_job(spec.job_name, trigger="interval", minutes=int(minutes))
        except Exception:  # noqa: BLE001
            log.exception("Failed to reschedule %s", spec.job_name)
    return intervals


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            log.exception("Failed to shut down scheduler cleanly")
        _scheduler = None


def restart_scheduler() -> dict[str, Any]:
    stop_scheduler()
    sched = start_scheduler()
    if sched is None:
        return {"ok": False, "reason": "scheduler disabled or failed to start"}
    return {
        "ok": True,
        "jobs": [j.id for j in sched.get_jobs()],
        "started_at": datetime.utcnow().isoformat(),
    }
