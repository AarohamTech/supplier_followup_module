"""Settings & mail engine control router.

Exposes:
  Legacy (preserved):
    GET  /api/settings/scheduler
    PUT  /api/settings/scheduler
    PUT  /api/settings/followup

  Mail engine control:
    GET  /api/settings/mail-engine
    POST /api/settings/test-smtp
    POST /api/settings/test-imap

  Cron job admin:
    GET  /api/settings/cron-jobs
    PUT  /api/settings/cron-jobs/{job_name}
    POST /api/settings/cron-jobs/{job_name}/run
    GET  /api/settings/cron-jobs/logs

  Engine lifecycle / health:
    POST /api/settings/engine/start
    POST /api/settings/engine/stop
    POST /api/settings/engine/restart
    GET  /api/settings/engine/health
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.deps import get_current_user, require_admin, require_manager
from ..database import get_db
from ..models.mail_template import MailTemplate
from ..scheduler import apply_scheduler_settings
from ..services import admin_digest_service, mail_config_service, mail_engine_service, settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Reads are available to any authenticated user; every write/control action
# below is gated to manager+ via this dependency list.
_MGR = [Depends(require_manager)]
# Editing the mailbox credentials themselves is admin-only.
_ADMIN = [Depends(require_admin)]


# ─────────────────────────────────────────────────────────────────────────────
# Legacy: scheduler/followup intervals (unchanged behavior)
# ─────────────────────────────────────────────────────────────────────────────
class SchedulerIntervalsPayload(BaseModel):
    MAIL_FETCH_INTERVAL_MINUTES: int | None = Field(default=None, ge=1)
    STATUS_CHANGE_INTERVAL_MINUTES: int | None = Field(default=None, ge=1)
    AUTO_REPLY_INTERVAL_MINUTES: int | None = Field(default=None, ge=1)
    MAIL_SEND_INTERVAL_MINUTES: int | None = Field(default=None, ge=1)


class FollowupIntervalsPayload(BaseModel):
    intervals: dict[str, int] = Field(default_factory=dict)


class DraftRulePayload(BaseModel):
    subject_template: str | None = Field(default=None, max_length=500)
    body_template: str | None = None
    active: bool | None = None
    interval_hours: int | None = Field(default=None, ge=1)


_DRAFT_STATUS_BY_TEMPLATE: dict[str, str] = {
    "GREEN_PO_RELEASE": "PENDING_ACK",
    "YELLOW_REMINDER": "REMINDER_DUE",
    "RED_DAY1": "URGENT_FOLLOWUP",
    "RED_DAY2": "STRONG_FOLLOWUP",
    "BLACK_ESCALATION": "CRITICAL_ESCALATION",
}

_DRAFT_SIGNAL_ORDER = {"GREEN": 0, "YELLOW": 1, "RED": 2, "BLACK": 3}


def _draft_rule_row(template: MailTemplate, intervals: dict[str, int]) -> dict:
    status = _DRAFT_STATUS_BY_TEMPLATE.get(template.template_name)
    return {
        "id": template.id,
        "template_name": template.template_name,
        "signal": template.signal,
        "day_no": template.day_no,
        "followup_status": status,
        "interval_hours": intervals.get(status) if status else None,
        "subject_template": template.subject_template,
        "body_template": template.body_template,
        "active": template.active,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


@router.get("/scheduler")
def get_scheduler_settings(db: Session = Depends(get_db)) -> dict:
    return {
        "scheduler_intervals_minutes": settings_service.get_scheduler_intervals(db),
        "followup_intervals_hours": settings_service.get_followup_intervals(db),
    }


@router.put("/scheduler", dependencies=_MGR)
def update_scheduler_intervals(
    payload: SchedulerIntervalsPayload,
    db: Session = Depends(get_db),
) -> dict:
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = settings_service.set_scheduler_intervals(db, values)
    apply_scheduler_settings()
    return {"scheduler_intervals_minutes": updated}


@router.put("/followup", dependencies=_MGR)
def update_followup_intervals(
    payload: FollowupIntervalsPayload,
    db: Session = Depends(get_db),
) -> dict:
    updated = settings_service.set_followup_intervals(db, payload.intervals)
    return {"followup_intervals_hours": updated}


# ─────────────────────────────────────────────────────────────────────────────
# Admin digest config
# ─────────────────────────────────────────────────────────────────────────────
class AdminDigestUpdate(BaseModel):
    enabled: bool | None = None
    recipients: list[str] | None = None
    send_hour: int | None = None
    timezone: str | None = None
    sections: dict[str, bool] | None = None
    limits: dict[str, int] | None = None


@router.get("/admin-digest")
def get_admin_digest_settings(db: Session = Depends(get_db)) -> dict:
    return {"admin_digest": settings_service.get_admin_digest(db)}


@router.put("/admin-digest", dependencies=_MGR)
def update_admin_digest_settings(
    payload: AdminDigestUpdate, db: Session = Depends(get_db)
) -> dict:
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    return {"admin_digest": settings_service.set_admin_digest(db, values)}


@router.post("/admin-digest/test", dependencies=_MGR)
def send_admin_digest_test(
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
) -> dict:
    if not current_user.email:
        raise HTTPException(status_code=400, detail="Your account has no email address.")
    return admin_digest_service.send_test_digest(db, current_user.email)


@router.get("/draft-rules")
def list_draft_rules(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(MailTemplate).where(
            MailTemplate.template_name.in_(list(_DRAFT_STATUS_BY_TEMPLATE.keys())),
        )
    ).all()
    intervals = settings_service.get_followup_intervals(db)
    rules = [_draft_rule_row(row, intervals) for row in rows]
    rules.sort(
        key=lambda item: (
            _DRAFT_SIGNAL_ORDER.get(str(item["signal"]).upper(), 99),
            item["day_no"],
            item["template_name"],
        )
    )
    return {"rules": rules, "followup_intervals_hours": intervals}


@router.put("/draft-rules/{template_id}", dependencies=_MGR)
def update_draft_rule(
    template_id: int,
    payload: DraftRulePayload,
    db: Session = Depends(get_db),
) -> dict:
    template = db.get(MailTemplate, template_id)
    if template is None or template.template_name not in _DRAFT_STATUS_BY_TEMPLATE:
        raise HTTPException(404, "Draft template not found")

    if payload.subject_template is not None:
        template.subject_template = payload.subject_template
    if payload.body_template is not None:
        template.body_template = payload.body_template
    if payload.active is not None:
        template.active = payload.active
    db.commit()

    status = _DRAFT_STATUS_BY_TEMPLATE.get(template.template_name)
    intervals = settings_service.get_followup_intervals(db)
    if status and payload.interval_hours is not None:
        intervals = settings_service.set_followup_intervals(db, {status: payload.interval_hours})

    db.refresh(template)
    return {"rule": _draft_rule_row(template, intervals)}


# ─────────────────────────────────────────────────────────────────────────────
# Mail engine snapshot + live tests
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/mail-engine")
def mail_engine_snapshot() -> dict:
    return mail_engine_service.mail_engine_snapshot()


@router.post("/test-smtp")
def test_smtp() -> dict:
    return mail_engine_service.test_smtp()


@router.post("/test-imap")
def test_imap() -> dict:
    return mail_engine_service.test_imap()


# ─────────────────────────────────────────────────────────────────────────────
# Main mailbox credentials (per-company; admin-only edit)
# ─────────────────────────────────────────────────────────────────────────────
class SmtpConfigPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = False
    host: str = ""
    port: int = Field(default=587, ge=0)
    user: str = ""
    from_addr: str = Field(default="", alias="from")
    # Blank/omitted keeps the stored password.
    password: str | None = None


class ImapConfigPayload(BaseModel):
    enabled: bool = False
    protocol: str = "IMAP"
    use_ssl: bool = False
    host: str = ""
    port: int = Field(default=0, ge=0)
    user: str = ""
    folder: str = "INBOX"
    password: str | None = None


@router.get("/mail-config")
def get_mail_config(db: Session = Depends(get_db)) -> dict:
    """Effective mail credentials for the current company (passwords masked)."""
    return {
        "smtp": mail_config_service.smtp_masked(db),
        "imap": mail_config_service.imap_masked(db),
    }


@router.put("/mail-config/smtp", dependencies=_ADMIN)
def put_smtp_config(payload: SmtpConfigPayload, db: Session = Depends(get_db)) -> dict:
    mail_config_service.set_smtp_config(
        db,
        enabled=payload.enabled,
        host=payload.host,
        port=payload.port,
        user=payload.user,
        from_addr=payload.from_addr,
        password=payload.password,
    )
    return {"smtp": mail_config_service.smtp_masked(db)}


@router.put("/mail-config/imap", dependencies=_ADMIN)
def put_imap_config(payload: ImapConfigPayload, db: Session = Depends(get_db)) -> dict:
    mail_config_service.set_imap_config(
        db,
        enabled=payload.enabled,
        protocol=payload.protocol,
        use_ssl=payload.use_ssl,
        host=payload.host,
        port=payload.port,
        user=payload.user,
        folder=payload.folder,
        password=payload.password,
    )
    return {"imap": mail_config_service.imap_masked(db)}


# ─────────────────────────────────────────────────────────────────────────────
# Cron job admin
# ─────────────────────────────────────────────────────────────────────────────
class CronJobPayload(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=1)


@router.get("/cron-jobs")
def list_cron_jobs(db: Session = Depends(get_db)) -> dict:
    return {"jobs": mail_engine_service.list_cron_jobs(db)}


@router.put("/cron-jobs/{job_name}", dependencies=_MGR)
def update_cron_job(
    job_name: str,
    payload: CronJobPayload,
    db: Session = Depends(get_db),
) -> dict:
    if payload.enabled is None and payload.interval_minutes is None:
        raise HTTPException(400, "Provide enabled and/or interval_minutes")
    updated = mail_engine_service.update_cron_job(
        db,
        job_name,
        enabled=payload.enabled,
        interval_minutes=payload.interval_minutes,
    )
    if updated is None:
        raise HTTPException(404, f"Unknown job: {job_name}")
    return updated


@router.post("/cron-jobs/{job_name}/run", dependencies=_MGR)
def run_cron_job_now(job_name: str) -> dict:
    result = mail_engine_service.run_cron_job_now(job_name)
    if result.get("status") == "ERROR" and "Unknown job" in (result.get("message") or ""):
        raise HTTPException(404, result["message"])
    return result


@router.post("/cron-jobs/run-all", dependencies=_MGR)
def run_all_cron_jobs(db: Session = Depends(get_db)) -> dict:
    return mail_engine_service.run_all_jobs(db)


@router.get("/cron-jobs/logs")
def cron_job_logs(
    db: Session = Depends(get_db),
    job_name: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    return {"logs": mail_engine_service.recent_job_logs(db, job_name=job_name, limit=limit)}


# ─────────────────────────────────────────────────────────────────────────────
# Engine lifecycle + consolidated health
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/engine/start", dependencies=_MGR)
def engine_start() -> dict:
    return mail_engine_service.start_engine()


@router.post("/engine/stop", dependencies=_MGR)
def engine_stop() -> dict:
    return mail_engine_service.stop_engine()


@router.post("/engine/restart", dependencies=_MGR)
def engine_restart() -> dict:
    return mail_engine_service.restart_engine()


@router.get("/engine/health")
def engine_health() -> dict:
    return mail_engine_service.engine_health()
