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
from sqlalchemy import select as _select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.tenant import use_company
from ..database import SessionLocal
from ..models.communication_message import CommunicationMessage
from ..models.engine_job import EngineJob
from ..models.status_change_log import StatusChangeLog
from ..services import (
    agent_subscription_service as agent_subs,
    ai_insights_service,
    communication_message_service as msg_service,
    engine_registry,
    hi_agent_tools,
    knowledge_indexer,
    mail_config_service,
    notification_service as notif,
    po_followup_mail_service,
    settings_service,
)
from ..services.crm_config import get_crm_config
from ..services.engine_registry import EngineJobSpec
from ..workers import mail_fetch_worker, mail_send_worker

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Job bodies (called by the registry wrapper)
# ─────────────────────────────────────────────────────────────────────────────
def _list_active_companies():
    """Read (code, schema_name, is_default) for active companies from the default
    (public) context. Isolated so tests can patch it."""
    from ..services import company_service
    db: Session = SessionLocal()
    try:
        return [(c.code, c.schema_name, c.is_default) for c in company_service.list_active(db)]
    finally:
        db.close()


def _active_companies() -> list[tuple[str, str, bool]]:
    try:
        rows = _list_active_companies()
        if rows:
            return rows
    except Exception:  # noqa: BLE001
        log.exception("Failed to list active companies; falling back to default")
    return [("102", "public", True)]


def mail_fetch_runner() -> dict[str, Any]:
    """Poll each active company's own mailbox. A company with no configured mailbox
    (and no env fallback — that only applies to the default schema) is skipped."""
    log.info("[cron] mail_fetch_runner starting")
    out: dict[str, Any] = {}
    for code, schema, _ in _active_companies():
        with use_company(schema):
            db: Session = SessionLocal()
            try:
                cfg = mail_config_service.get_imap_config(db)
            finally:
                db.close()
            ready, reason = cfg.ready()
            if not ready:
                out[code] = {"enabled": False, "reason": reason, "fetched": 0, "processed": []}
                continue
            out[code] = mail_fetch_worker.fetch_supplier_mails(cfg)
    log.info("[cron] mail_fetch_runner done: %s", out)
    return out


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
    out: dict[str, Any] = {}
    for code, schema, _ in _active_companies():
        with use_company(schema):
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
                out[code] = {
                    "ran_at": datetime.utcnow().isoformat(),
                    "drafts_created": created,
                    "queued": created,
                }
            except Exception:  # noqa: BLE001
                log.exception("auto_reply_runner failed for %s", code)
                db.rollback()
                out[code] = {
                    "ran_at": datetime.utcnow().isoformat(),
                    "drafts_created": created,
                    "error": True,
                }
            finally:
                db.close()
    return out


def mail_send_runner() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for code, schema, _ in _active_companies():
        with use_company(schema):
            out[code] = mail_send_worker.send_ready_messages(schema=schema)
    return out


def po_followup_mail_runner() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for code, schema, _ in _active_companies():
        with use_company(schema):
            db: Session = SessionLocal()
            try:
                out[code] = po_followup_mail_service.queue_due_po_followups(db)
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("po_followup_mail_runner failed for %s", code)
                out[code] = {"enabled": True, "queued": 0, "skipped": 0, "error": True}
            finally:
                db.close()
    return out


def delay_risk_runner() -> dict[str, Any]:
    """Recompute predictive delay-risk scores per company."""
    out: dict[str, Any] = {}
    for code, schema, _ in _active_companies():
        with use_company(schema):
            db: Session = SessionLocal()
            try:
                out[code] = ai_insights_service.rescore_all(db)
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("delay_risk_runner failed for %s", code)
                out[code] = {"updated": 0, "error": True}
            finally:
                db.close()
    return out


def knowledge_index_runner() -> dict[str, Any]:
    """Embed any new customer mails / supplier replies into the vector store."""
    if not knowledge_indexer.enabled():
        return {"enabled": False, "indexed": 0, "skipped": 0}
    db: Session = SessionLocal()
    try:
        result = knowledge_indexer.backfill(db, limit=200)
        log.info("[cron] knowledge_index_runner done: %s", result)
        return result
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("knowledge_index_runner failed")
        return {"indexed": 0, "error": True}
    finally:
        db.close()


def crm_ingestion_runner() -> dict[str, Any]:
    """Poll each active company's CRM desk feed and upsert into its schema."""
    if not getattr(settings, "CRM_INGEST_ENABLED", False):
        return {"enabled": False, "status": "DISABLED"}
    from ..services import crm_ingest_service

    out: dict[str, Any] = {}
    for code, schema, is_default in _active_companies():
        cfg = get_crm_config(code, is_default=is_default)
        if cfg is None:
            out[code] = {"status": "SKIPPED", "reason": "no CRM config"}
            continue
        with use_company(schema):
            db: Session = SessionLocal()
            try:
                out[code] = crm_ingest_service.poll_and_ingest(db, cfg, desk_label=code)
            except Exception:  # noqa: BLE001
                db.rollback()
                log.exception("crm ingest failed for company %s", code)
                out[code] = {"ok": False, "status": "ERROR"}
            finally:
                db.close()
    return out


def courier_tracking_runner() -> dict[str, Any]:
    """Poll the courier tracking API for in-transit ASNs and append checkpoints."""
    if not getattr(settings, "COURIER_API_ENABLED", False):
        return {"enabled": False, "status": "DISABLED"}
    db: Session = SessionLocal()
    try:
        from ..services import courier_tracking_service

        result = courier_tracking_service.poll_in_transit(db)
        log.info("[cron] courier_tracking_runner done: %s", result)
        return result
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("courier_tracking_runner failed")
        return {"ok": False, "status": "ERROR", "error": True}
    finally:
        db.close()


def admin_digest_runner() -> dict[str, Any]:
    """Send the Harmony Intelligence Summary if it is due (once per local day)."""
    db: Session = SessionLocal()
    try:
        from ..services import admin_digest_service

        result = admin_digest_service.send_digest_if_due(db)
        log.info("[cron] admin_digest_runner done: %s", result)
        return result
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("admin_digest_runner failed")
        return {"sent": 0, "error": True}
    finally:
        db.close()


def _dispatch_followups(db: Session) -> int:
    """Forward each new thread message to every ACTIVE FOLLOWUP subscriber."""
    forwarded = 0
    for sub in agent_subs.list_active(db, "FOLLOWUP"):
        hwm = sub.last_forwarded_message_id or 0
        stmt = _select(CommunicationMessage).where(CommunicationMessage.id > hwm)
        if sub.procurement_record_id is not None and sub.supplier_po_no:
            stmt = stmt.where(
                (CommunicationMessage.procurement_record_id == sub.procurement_record_id)
                | (CommunicationMessage.supplier_po_no == sub.supplier_po_no)
            )
        elif sub.procurement_record_id is not None:
            stmt = stmt.where(CommunicationMessage.procurement_record_id == sub.procurement_record_id)
        elif sub.supplier_po_no:
            stmt = stmt.where(CommunicationMessage.supplier_po_no == sub.supplier_po_no)
        else:
            continue
        new_msgs = list(db.scalars(stmt.order_by(CommunicationMessage.id.asc())).all())
        if not new_msgs:
            continue
        for m in new_msgs:
            if not sub.recipient_email:
                continue
            who = "Supplier" if m.direction == "INCOMING" else "Procurement"
            fwd = msg_service.queue_outgoing_message(
                db,
                procurement_record_id=sub.procurement_record_id,
                supplier_po_no=sub.supplier_po_no,
                subject=f"[Followup] PO {sub.supplier_po_no}: {m.subject or 'new message'}",
                body=f"New message from {who} on PO {sub.supplier_po_no}:\n\n{(m.body or '').strip()}",
                to_emails=[sub.recipient_email],
                mail_type="HI_FOLLOWUP_FORWARD",
                commit=True,
            )
            mail_send_worker.send_message_now(db, fwd.id)
            if sub.recipient_user_id:
                notif.safe(
                    notif.notify_users, db, [sub.recipient_user_id],
                    type="HI_FOLLOWUP",
                    title=f"New message on PO {sub.supplier_po_no}",
                    body=(m.body or "")[:140],
                    link="/mail-history",
                    supplier_po_no=sub.supplier_po_no,
                    procurement_record_id=sub.procurement_record_id,
                )
            forwarded += 1
        agent_subs.advance_followup(db, sub, new_msgs[-1].id)
    return forwarded


def _dispatch_summaries(db: Session, now: datetime) -> int:
    """Send a thread summary to each due SCHEDULED_SUMMARY subscriber."""
    sent = 0
    for sub in agent_subs.due_summaries(db, now):
        ctx = hi_agent_tools.ToolContext(
            db=db, user=None, supplier_id=sub.supplier_id,
            procurement_record_id=sub.procurement_record_id,
            supplier_po_no=sub.supplier_po_no,
        )
        summary = hi_agent_tools.tool_summarize(ctx, {}).get("summary") or "No new activity."
        if sub.recipient_email:
            msg = msg_service.queue_outgoing_message(
                db,
                procurement_record_id=sub.procurement_record_id,
                supplier_po_no=sub.supplier_po_no,
                subject=f"[Summary] PO {sub.supplier_po_no}",
                body=summary,
                to_emails=[sub.recipient_email],
                mail_type="HI_SCHEDULED_SUMMARY",
                commit=True,
            )
            mail_send_worker.send_message_now(db, msg.id)
            if sub.recipient_user_id:
                notif.safe(
                    notif.notify_users, db, [sub.recipient_user_id],
                    type="HI_SUMMARY",
                    title=f"Scheduled summary: PO {sub.supplier_po_no}",
                    body=summary[:140], link="/mail-history",
                    supplier_po_no=sub.supplier_po_no,
                    procurement_record_id=sub.procurement_record_id,
                )
        agent_subs.mark_summary_dispatched(db, sub, now)
        sent += 1
    return sent


def agent_dispatch_runner() -> dict[str, Any]:
    """Forward followup messages and send due scheduled summaries."""
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        forwarded = _dispatch_followups(db)
        summaries = _dispatch_summaries(db, now)
        return {"ran_at": now.isoformat(), "forwarded": forwarded, "summaries": summaries}
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("agent_dispatch_runner failed")
        return {"forwarded": 0, "summaries": 0, "error": True}
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
    EngineJobSpec(
        job_name="delay_risk_cron",
        display_name="Delay Risk Scorer",
        description="Recompute predictive delivery-delay risk for all records.",
        default_interval_minutes=60,
        runner=delay_risk_runner,
        category="STATUS",
    ),
    EngineJobSpec(
        job_name="knowledge_index_cron",
        display_name="Knowledge Indexer",
        description="Embed new mails/replies into the pgvector memory (RAG).",
        default_interval_minutes=30,
        runner=knowledge_index_runner,
        category="OTHER",
    ),
    EngineJobSpec(
        job_name="crm_ingestion_cron",
        display_name="CRM Purchase Order Sync",
        description="Poll the Hariom CRM desk feed and upsert generated POs live.",
        default_interval_minutes=int(getattr(settings, "CRM_INGEST_INTERVAL_MINUTES", 3) or 3),
        runner=crm_ingestion_runner,
        category="PROCUREMENT",
    ),
    EngineJobSpec(
        job_name="agent_dispatch_cron",
        display_name="HI Agent Dispatch",
        description="Forward followup messages and send due scheduled summaries.",
        default_interval_minutes=int(getattr(settings, "AGENT_DISPATCH_INTERVAL_MINUTES", 5) or 5),
        runner=agent_dispatch_runner,
        category="OTHER",
    ),
    EngineJobSpec(
        job_name="admin_digest_cron",
        display_name="Harmony Intelligence Summary",
        description="Email the daily admin digest to configured recipients at the set hour.",
        default_interval_minutes=15,
        runner=admin_digest_runner,
        category="OTHER",
    ),
    EngineJobSpec(
        job_name="courier_tracking_cron",
        display_name="Courier Shipment Tracking",
        description="Poll the courier API for in-transit ASNs and append tracking checkpoints.",
        default_interval_minutes=int(getattr(settings, "COURIER_TRACKING_INTERVAL_MINUTES", 30) or 30),
        runner=courier_tracking_runner,
        category="SHIPMENT",
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
