"""Who may see a Task Manager task — the single source of truth.

Client rule (2026-11 feedback):
  * Admins (staff role ``admin``) see every task, open or done.
  * Everyone else — non-admin staff (manager / user / viewer) and employee-portal
    accounts — sees only the tasks they are *involved* in: they created it, are
    assigned to it, assigned it to someone, or watch it.
  * Completed (``DONE``) tasks are hidden from non-admin boards, lists, counters
    and exports. They stay reachable by id for the people involved, so a task
    that was just closed can still be reopened from its detail view.

The same "involved" set is the audience for task notifications
(``notification_service.notify_task_involved``), so a person is notified about
exactly the tasks they can see.

Pure service layer, portable SQL only (the test suite runs on SQLite).
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import String, cast, or_
from sqlalchemy.sql import Select

from ..core import roles as roles_mod
from ..core.account_kind import is_staff_account
from ..core.roles import Role
from ..models.communication_task import CommunicationTask
from ..models.user import User

DONE = "DONE"


def is_task_admin(user: Optional[User]) -> bool:
    """True for an internal staff account with the ``admin`` role.

    Portal accounts (supplier / employee) are never admins, whatever their role
    string says — mirrors ``core.deps.get_current_staff``.
    """
    if user is None:
        return False
    if not is_staff_account(user):
        return False
    return roles_mod.role_at_least(user.role, Role.ADMIN)


def watcher_ids(task: CommunicationTask) -> set[int]:
    out: set[int] = set()
    for w in task.watchers or []:
        try:
            out.add(int(w))
        except (TypeError, ValueError):
            continue  # legacy free-text watcher names
    return out


def involved_user_ids(task: CommunicationTask) -> set[int]:
    """Creator + assigner + assignee + watchers (user ids, no Nones)."""
    ids = {
        task.created_by_user_id,
        task.assigned_by_user_id,
        task.assigned_to_user_id,
    }
    ids |= watcher_ids(task)
    return {i for i in ids if i is not None}


def is_involved(user: User, task: CommunicationTask) -> bool:
    return user.id in involved_user_ids(task)


def can_see(user: User, task: CommunicationTask) -> bool:
    """May `user` open this task by id (detail, edit, comments, files)?"""
    return is_task_admin(user) or is_involved(user, task)


def involved_clause(user_id: int):
    """SQL predicate: `user_id` created / is assigned / assigned / watches.
    The watcher part is a coarse LIKE on the JSON text (portable across
    Postgres and SQLite); pair with ``is_involved`` for an exact answer."""
    T = CommunicationTask
    return or_(
        T.created_by_user_id == user_id,
        T.assigned_by_user_id == user_id,
        T.assigned_to_user_id == user_id,
        cast(T.watchers, String).like(f"%{user_id}%"),
    )


def scope_stmt(stmt: Select, user: User, *, include_done: Optional[bool] = None) -> Select:
    """Narrow a ``select(CommunicationTask)`` (or a count over it) to `user`.

    Admins: unchanged (``include_done`` False drops DONE if asked explicitly).
    Others: involved-only, DONE excluded. The watcher match is a coarse LIKE
    pre-filter on the JSON text — always follow a row query with
    ``filter_visible`` to drop false positives (user 5 vs watcher 15).
    """
    T = CommunicationTask
    admin = is_task_admin(user)
    if include_done is None:
        include_done = admin
    if not admin:
        stmt = stmt.where(involved_clause(user.id))
    if not include_done:
        stmt = stmt.where(or_(T.status.is_(None), T.status != DONE))
    return stmt


def filter_visible(
    rows: Iterable[CommunicationTask], user: User, *, include_done: Optional[bool] = None
) -> list[CommunicationTask]:
    """Exact (Python) version of ``scope_stmt`` for already-loaded rows."""
    admin = is_task_admin(user)
    if include_done is None:
        include_done = admin
    out: list[CommunicationTask] = []
    for t in rows:
        if not admin and not is_involved(user, t):
            continue
        if not include_done and (t.status or "").upper() == DONE:
            continue
        out.append(t)
    return out
