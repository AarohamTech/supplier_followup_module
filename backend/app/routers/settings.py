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
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..scheduler import apply_scheduler_settings
from ..services import mail_engine_service, settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


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


@router.get("/scheduler")
def get_scheduler_settings(db: Session = Depends(get_db)) -> dict:
    return {
        "scheduler_intervals_minutes": settings_service.get_scheduler_intervals(db),
        "followup_intervals_hours": settings_service.get_followup_intervals(db),
    }


@router.put("/scheduler")
def update_scheduler_intervals(
    payload: SchedulerIntervalsPayload,
    db: Session = Depends(get_db),
) -> dict:
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = settings_service.set_scheduler_intervals(db, values)
    apply_scheduler_settings()
    return {"scheduler_intervals_minutes": updated}


@router.put("/followup")
def update_followup_intervals(
    payload: FollowupIntervalsPayload,
    db: Session = Depends(get_db),
) -> dict:
    updated = settings_service.set_followup_intervals(db, payload.intervals)
    return {"followup_intervals_hours": updated}


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
# Cron job admin
# ─────────────────────────────────────────────────────────────────────────────
class CronJobPayload(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=1)


@router.get("/cron-jobs")
def list_cron_jobs(db: Session = Depends(get_db)) -> dict:
    return {"jobs": mail_engine_service.list_cron_jobs(db)}


@router.put("/cron-jobs/{job_name}")
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


@router.post("/cron-jobs/{job_name}/run")
def run_cron_job_now(job_name: str) -> dict:
    result = mail_engine_service.run_cron_job_now(job_name)
    if result.get("status") == "ERROR" and "Unknown job" in (result.get("message") or ""):
        raise HTTPException(404, result["message"])
    return result


@router.post("/cron-jobs/run-all")
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
@router.post("/engine/start")
def engine_start() -> dict:
    return mail_engine_service.start_engine()


@router.post("/engine/stop")
def engine_stop() -> dict:
    return mail_engine_service.stop_engine()


@router.post("/engine/restart")
def engine_restart() -> dict:
    return mail_engine_service.restart_engine()


@router.get("/engine/health")
def engine_health() -> dict:
    return mail_engine_service.engine_health()
