"""The ZanFlow bridge.

ZanFlow Materials (the material-enquiry system) assigns a material line to a
person; that person needs to see it here, in the portal they already work in.
This module is both halves of that exchange:

    in    `upsert_external_task` — one task per material line, keyed on
          `(external_system, external_ref)`, called from `routers/bridge.py`
    out   `notify_zanflow` — status, progress and comments going back, called
          from the two chokepoints in `routers/communication.py`

Nothing here knows about material lines, stages or MDNs. The vocabulary is
translated on the ZanFlow side before it arrives, so this stays a task system
that happens to accept tasks from somewhere else.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.communication_task import CommunicationTask
from ..models.user import User
from . import task_assignment_service as assign

log = logging.getLogger(__name__)

#: The one system allowed through the bridge today. Kept as a tuple rather than
#: a bare string so adding a second is a data change, not a code change.
KNOWN_SYSTEMS = ("zanflow",)

#: Fields ZanFlow owns for the whole life of the task. Everything else —
#: status, progress, signal, watchers — belongs to whoever works it here.
_OWNED_BY_SOURCE = ("title", "description", "material_name", "priority",
                    "due_date", "external_url", "assigned_by")


# --------------------------------------------------------------------------- #
# Inbound: ZanFlow → here
# --------------------------------------------------------------------------- #


def find_external_task(
    db: Session, *, external_system: str, external_ref: str
) -> CommunicationTask | None:
    return db.scalars(
        select(CommunicationTask)
        .where(
            CommunicationTask.external_system == external_system,
            CommunicationTask.external_ref == external_ref,
        )
        .order_by(CommunicationTask.id)
        .limit(1)
    ).first()


def _resolve_assignee(db: Session, assignee: dict | None) -> tuple[int | None, str | None]:
    """Find the account this task belongs to, or admit that we cannot.

    Three branches, in order: the id ZanFlow cached, the email, then nothing.
    The id is tried first because it is explicit — an administrator chose it —
    but it is only a cache of a decision, so a stale one falls through to the
    email rather than dropping the task. Returning `(None, display_name)` is a
    legitimate outcome: the task exists on the staff board with a name on it,
    and the admin screen on the ZanFlow side lists it as needing a mapping.
    """
    if not assignee:
        return None, None

    display = (assignee.get("display_name") or "").strip() or None

    user_id = assignee.get("followup_user_id")
    if user_id is not None:
        try:
            user, name = assign.resolve_assignee(db, int(user_id))
            return user.id, name
        except (ValueError, TypeError):
            pass  # stale or unassignable — fall through to the email

    email = (assignee.get("email") or "").strip()
    if email:
        user = db.scalars(
            select(User).where(
                func.lower(User.email) == email.lower(),
                User.is_active.is_(True),
                User.supplier_id.is_(None),
            )
        ).first()
        if user is not None:
            return user.id, assign.display_name(user)

    return None, display


def _signal_for(priority: str | None) -> str:
    return {"HIGH": "RED", "MEDIUM": "YELLOW"}.get((priority or "").upper(), "GREEN")


def upsert_external_task(
    db: Session,
    *,
    external_system: str,
    external_ref: str,
    title: str,
    external_url: str | None = None,
    description: str | None = None,
    material_name: str | None = None,
    priority: str = "MEDIUM",
    status: str = "TODO",
    due_date: datetime | None = None,
    assignee: dict | None = None,
    assigned_by: str | None = None,
    commit: bool = False,
) -> tuple[CommunicationTask, bool, bool]:
    """Create or update the task mirroring one external record.

    Returns `(task, created, unmapped_assignee)`.

    `status` seeds a new task and is then never written again: after the first
    push the people working the task own its status, and re-stamping it on
    every edit ZanFlow makes would undo their work from a distance.
    """
    row = find_external_task(db, external_system=external_system, external_ref=external_ref)
    created = row is None

    assignee_id, assignee_name = _resolve_assignee(db, assignee)
    unmapped = bool(assignee) and assignee_id is None

    if created:
        row = CommunicationTask(
            external_system=external_system,
            external_ref=external_ref,
            task_source="INTERNAL",
            status=status,
        )
        db.add(row)

    row.title = title
    row.description = description
    row.material_name = material_name
    row.priority = priority
    row.signal = _signal_for(priority)
    row.due_date = due_date
    row.external_url = external_url
    row.assigned_by = assigned_by

    # Reassignment travels; un-assignment does not. ZanFlow cannot clear an
    # assignee it never resolved, or a task would silently lose its owner here
    # every time an unmapped user touched the line.
    if assignee_id is not None and assignee_id != row.assigned_to_user_id:
        row.assigned_to_user_id = assignee_id
        row.assigned_to = assignee_name
        row.assigned_at = datetime.utcnow()
    elif created:
        row.assigned_to = assignee_name

    db.flush()
    if commit:
        db.commit()
        db.refresh(row)
    return row, created, unmapped


# --------------------------------------------------------------------------- #
# Outbound: here → ZanFlow
# --------------------------------------------------------------------------- #

#: Path on the ZanFlow API. Its prefix is fixed by that app's `API_PREFIX`.
_CALLBACK_PATH = "/api/v1/zanflow/integrations/followup/callback"


def notify_zanflow(
    db: Session,
    task: CommunicationTask | None,
    *,
    event: str,
    status: str | None = None,
    progress_percent: int | None = None,
    comment: str | None = None,
    actor: str | None = None,
    actor_user_id: int | None = None,
) -> bool:
    """Tell ZanFlow that a bridged task moved. Best effort, never fatal.

    Called from inside a request a person is waiting on, so every failure path
    ends in a log line and a `False`. A ZanFlow outage must not make a portal
    user's status change fail — and it does not need to, because the callback
    carries current state rather than a delta: the next change re-sends
    everything and the mirror heals itself.
    """
    if task is None or task.external_system not in KNOWN_SYSTEMS or not task.external_ref:
        return False

    base = (settings.ZANFLOW_API_BASE or "").strip().rstrip("/")
    secret = (settings.ZANFLOW_CALLBACK_SECRET or "").strip()
    if not base or not secret:
        return False

    body: dict[str, Any] = {
        "external_ref": task.external_ref,
        "task_id": task.id,
        "event": event,
        "status": status if status is not None else task.status,
        "progress_percent": (
            progress_percent if progress_percent is not None else task.progress_percent
        ),
        "comment": comment,
        "actor": actor,
        # ZanFlow stores this id against its own users, so it can turn a
        # comment made here into a comment authored by the right person there.
        # Its `zf_comments.author_id` is NOT NULL — without this the discussion
        # could only cross as an anonymous activity line.
        "actor_user_id": actor_user_id,
        "occurred_at": datetime.utcnow().isoformat(),
    }

    try:
        response = requests.post(
            f"{base}{_CALLBACK_PATH}",
            json=body,
            headers={"X-Bridge-Secret": secret},
            timeout=settings.ZANFLOW_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            log.warning(
                "bridge: ZanFlow rejected callback for %s (%s): %s",
                task.external_ref, response.status_code, response.text[:200],
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — every transport failure is the same non-event
        log.warning("bridge: ZanFlow callback failed for %s: %s", task.external_ref, exc)
        return False


def safe_notify(db: Session, task: CommunicationTask | None, **kw) -> None:
    """`notify_zanflow` with the last exception boundary, for router call sites.

    `notify_zanflow` already swallows transport errors; this also swallows the
    programming ones, so a bad keyword in a call site can never take down a
    task update.
    """
    try:
        notify_zanflow(db, task, **kw)
    except Exception:  # noqa: BLE001
        log.exception("bridge: callback raised unexpectedly")
