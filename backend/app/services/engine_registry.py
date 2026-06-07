"""Engine job registry — single source of truth for all cron jobs.

Each registered job has:
  - a stable `job_name` key
  - a callable `runner` (returns a dict that may include record counts)
  - a `default_interval_minutes` used when no DB row exists yet
  - a human-readable display name + description

The registry is independent of APScheduler: scheduling code reads from
the registry, while the runner wrapper handles per-run logging into
`engine_jobs` and `engine_job_logs`.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.engine_job import EngineJob, EngineJobLog

log = logging.getLogger(__name__)


JobRunner = Callable[[], dict[str, Any] | None]


@dataclass
class EngineJobSpec:
    job_name: str
    display_name: str
    description: str
    default_interval_minutes: int
    runner: JobRunner
    category: str = "MAIL"  # MAIL / STATUS / FOLLOWUP / OTHER


_REGISTRY: dict[str, EngineJobSpec] = {}
_RUN_LOCK = threading.Lock()


def register(spec: EngineJobSpec) -> None:
    _REGISTRY[spec.job_name] = spec


def all_specs() -> list[EngineJobSpec]:
    return list(_REGISTRY.values())


def get_spec(job_name: str) -> EngineJobSpec | None:
    return _REGISTRY.get(job_name)


def ensure_job_rows(db: Session) -> list[EngineJob]:
    """Make sure each registered spec has a matching `engine_jobs` row.

    Existing rows are left intact (admin-edited values like enabled/interval
    must survive restarts).
    """
    rows: list[EngineJob] = []
    for spec in _REGISTRY.values():
        existing = db.scalars(
            select(EngineJob).where(EngineJob.job_name == spec.job_name)
        ).first()
        if existing:
            existing.display_name = spec.display_name
            existing.description = spec.description
            rows.append(existing)
            continue
        row = EngineJob(
            job_name=spec.job_name,
            display_name=spec.display_name,
            description=spec.description,
            enabled=True,
            interval_minutes=spec.default_interval_minutes,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


def list_jobs(db: Session) -> list[EngineJob]:
    rows = list(db.scalars(select(EngineJob).order_by(EngineJob.id.asc())).all())
    rows_by_name = {r.job_name for r in rows}
    missing = [s for s in _REGISTRY.values() if s.job_name not in rows_by_name]
    if missing:
        ensure_job_rows(db)
        rows = list(db.scalars(select(EngineJob).order_by(EngineJob.id.asc())).all())
    return rows


def get_job(db: Session, job_name: str) -> EngineJob | None:
    return db.scalars(select(EngineJob).where(EngineJob.job_name == job_name)).first()


def update_job(
    db: Session,
    job_name: str,
    *,
    enabled: bool | None = None,
    interval_minutes: int | None = None,
) -> EngineJob | None:
    row = get_job(db, job_name)
    if row is None:
        return None
    if enabled is not None:
        row.enabled = bool(enabled)
    if interval_minutes is not None and interval_minutes >= 1:
        row.interval_minutes = int(interval_minutes)
    db.commit()
    db.refresh(row)
    return row


def _extract_counts(result: Any) -> tuple[int, int, int]:
    """Best-effort projection of a runner's return dict into counters."""
    if not isinstance(result, dict):
        return 0, 0, 0
    processed = (
        result.get("attempted")
        or result.get("processed")
        or result.get("queued")
        or 0
    )
    if isinstance(processed, list):
        processed = len(processed)
    success = result.get("success_count")
    if success is None:
        results = result.get("results")
        if isinstance(results, list):
            success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "SENT")
        else:
            success = 0
    failed = result.get("failed_count")
    if failed is None:
        results = result.get("results")
        if isinstance(results, list):
            failed = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "FAILED")
        else:
            failed = 0
    try:
        return int(processed or 0), int(success or 0), int(failed or 0)
    except (TypeError, ValueError):
        return 0, 0, 0


def run_job(
    job_name: str,
    *,
    manual: bool = False,
    next_run_at: datetime | None = None,
) -> dict[str, Any]:
    """Execute a registered job runner and persist start/finish state.

    Returns a dict with: ok, status, message, records_processed, records_success,
    records_failed, started_at, finished_at, result.
    """
    spec = _REGISTRY.get(job_name)
    if spec is None:
        return {
            "ok": False,
            "status": "ERROR",
            "message": f"Unknown job: {job_name}",
        }

    started = datetime.utcnow()
    log_row: EngineJobLog | None = None
    job_row: EngineJob | None = None
    db: Session | None = None
    try:
        db = SessionLocal()
    except Exception:  # noqa: BLE001
        log.exception("engine_job: could not open DB session for %s", job_name)
        db = None

    if db is not None:
        try:
            job_row = get_job(db, job_name)
            if job_row is None:
                ensure_job_rows(db)
                job_row = get_job(db, job_name)

            if job_row is not None and not job_row.enabled and not manual:
                db.close()
                return {
                    "ok": False,
                    "status": "DISABLED",
                    "message": f"{job_name} is disabled",
                }

            log_row = EngineJobLog(
                job_name=job_name,
                started_at=started,
                status="RUNNING",
            )
            db.add(log_row)
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("engine_job pre-run logging failed for %s", job_name)
            db.rollback()
        finally:
            db.close()

    result: Any = None
    error: str | None = None
    status = "OK"
    with _RUN_LOCK if False else _NULL_LOCK:  # serialization opt-in: kept loose
        try:
            result = spec.runner()
        except Exception as exc:  # noqa: BLE001
            log.exception("engine_job runner failed: %s", job_name)
            error = str(exc)
            status = "ERROR"

    finished = datetime.utcnow()
    processed, success, failed = _extract_counts(result)

    try:
        db = SessionLocal()
    except Exception:  # noqa: BLE001
        log.exception("engine_job: could not open DB session post-run for %s", job_name)
        db = None

    if db is not None:
        try:
            if log_row is not None:
                persisted = db.get(EngineJobLog, log_row.id)
                if persisted is not None:
                    persisted.finished_at = finished
                    persisted.status = status
                    persisted.records_processed = processed
                    persisted.records_success = success
                    persisted.records_failed = failed
                    if error:
                        persisted.error_detail = error
                    else:
                        persisted.message = _short_message(result)
            job_row = get_job(db, job_name)
            if job_row is not None:
                job_row.last_run_at = finished
                job_row.last_status = status
                job_row.last_message = error or _short_message(result)
                job_row.total_runs = (job_row.total_runs or 0) + 1
                if status == "ERROR":
                    job_row.failed_runs = (job_row.failed_runs or 0) + 1
                if next_run_at is not None:
                    job_row.next_run_at = next_run_at
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("engine_job post-run logging failed for %s", job_name)
            db.rollback()
        finally:
            db.close()

    return {
        "ok": status == "OK",
        "status": status,
        "message": error or _short_message(result),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "records_processed": processed,
        "records_success": success,
        "records_failed": failed,
        "result": result if isinstance(result, dict) else None,
    }


class _NoLock:
    def __enter__(self):  # noqa: D401
        return self

    def __exit__(self, *args):  # noqa: D401
        return False


_NULL_LOCK = _NoLock()


def _short_message(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    if reason := result.get("reason"):
        return str(reason)[:240]
    if result.get("attempted") is not None:
        attempted = result.get("attempted")
        return f"attempted={attempted}"
    if result.get("queued") is not None:
        return f"queued={result.get('queued')} skipped={result.get('skipped', 0)}"
    if result.get("fetched") is not None:
        return f"fetched={result.get('fetched')}"
    return None


def recent_logs(db: Session, *, job_name: str | None = None, limit: int = 50) -> list[EngineJobLog]:
    stmt = select(EngineJobLog).order_by(EngineJobLog.id.desc()).limit(limit)
    if job_name:
        stmt = stmt.where(EngineJobLog.job_name == job_name)
    return list(db.scalars(stmt).all())
