# Jira-like Task Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing `communication_task` board into a Jira-like tracker: real-user assignees (staff + employees) replacing dummy strings, a unified activity timeline, manual progress %, AI summaries, and an analytics dashboard with Excel export — all backed by the existing append-only activity log.

**Architecture:** Additive, online-migrated schema changes (new nullable columns added by `core/schema_evolve.ensure_columns` on boot — no Alembic). The activity log (`task_activity_logs`) stays the single source of truth for "log everything"; we extend its event vocabulary and stamp a real actor `user_id`. New read/derive endpoints (assignees, analytics, export, ai-summary) live in the existing `communication.py` router. The frontend adds an assignee-picker, a progress bar, an AI-summary panel, a merged timeline, and a new analytics page.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Pydantic v2, openpyxl (already a dep), pytest + unittest (in-memory SQLite, no conftest), Next.js 14 App Router + TypeScript + Tailwind, Zustand.

## Global Constraints

- **Python invocation:** run all backend commands from `backend/` using `.venv/Scripts/python.exe` (python is NOT on PATH). Tests: `.venv/Scripts/python.exe -m pytest tests/<file> -q`.
- **Tests are self-contained:** no `conftest.py`. Use `unittest` + in-memory SQLite via the `_temp_db()` pattern in `backend/tests/test_task_collaboration.py`. Import models through `app.models` and `Base` through `app.database` so `Base.metadata.create_all` builds the full schema.
- **Schema migrations:** never write Alembic. Add columns as `nullable=True` (or with a scalar default) on the model; `schema_evolve.ensure_columns` ALTERs them in on boot for both SQLite and Postgres.
- **Assignable users = staff + employees only:** `is_active = true` AND `supplier_id IS NULL`. Suppliers are never assignable and never see assignees/analytics.
- **Auth/actor:** internal routers are mounted with `_rbac = [Depends(require_writer_for_writes)]` (method-aware; portal accounts rejected). Inside handlers that must record an actor, add `actor: User = Depends(get_current_staff)`.
- **Denormalized display name:** whenever `assigned_to_user_id` is set, also set `assigned_to` to the user's `full_name` (fallback `username`, then `email`) and stamp `assigned_at`.
- **Frontend checks:** `cd frontend && npm run build` must pass; there is no jest — TypeScript compile via build is the test. Use markdown `[text](path)` for any code references in PRs.
- **No PII commits:** never `git add -A`. Stage explicit paths. `docs/Hariom Employee details.xlsx` is gitignored and must stay uncommitted.
- **Deploy:** push to `main` triggers GitHub Actions → Mumbai EC2. Only push with explicit user authorization.

---

## File Structure

**Backend — modify:**
- `app/models/communication_task.py` — add `assigned_to_user_id`, `assigned_at`, `progress_percent`, `ai_summary`, `ai_summary_at`, `ai_summary_by`.
- `app/models/task_collaboration.py` — add `created_by_id` to `TaskComment` and `TaskActivityLog`; extend `TASK_ACTIVITY_TYPES`.
- `app/schemas/communication_task.py` — expose new fields on Base/Create/Update/Out.
- `app/services/task_collaboration_service.py` — `created_by_id` support; new activity types in `field_map`; `build_transcript()`.
- `app/services/task_assignment_service.py` *(new)* — `list_assignees()`, `resolve_assignee()`.
- `app/services/task_analytics_service.py` *(new)* — `compute_analytics()`, `export_workbook()`.
- `app/routers/communication.py` — add `/assignees`, `/analytics`, `/analytics/export`, `/tasks/{id}/ai-summary`; thread actor + assignee resolution + progress logging through create/update/comment.
- `app/routers/communication_hub.py` — escalation assigns a real user id.
- `app/seed.py` — seed `Purchase Head` / `Sourcing Head` manager accounts.

**Backend — new script:** `app/../scripts/remap_task_assignees.py` (i.e. `backend/scripts/remap_task_assignees.py`).

**Backend — new tests:** `tests/test_task_assignment.py`, `tests/test_task_analytics.py`, `tests/test_task_ai_summary.py`; extend `tests/test_task_collaboration.py`.

**Frontend — modify:** `lib/types.ts`, `lib/api.ts`, `app/tasks/page.tsx`, `components/layout/Sidebar.tsx`.
**Frontend — new:** `components/tasks/AssigneePicker.tsx`, `app/tasks/analytics/page.tsx`.

---

## Task 1: Schema — new task & collaboration columns

**Files:**
- Modify: `backend/app/models/communication_task.py`
- Modify: `backend/app/models/task_collaboration.py`
- Test: `backend/tests/test_task_schema.py` (create)

**Interfaces:**
- Produces: `CommunicationTask.assigned_to_user_id: int|None`, `.assigned_at: datetime|None`, `.progress_percent: int` (default 0), `.ai_summary: str|None`, `.ai_summary_at: datetime|None`, `.ai_summary_by: str|None`; `TaskComment.created_by_id: int|None`; `TaskActivityLog.created_by_id: int|None`; `TASK_ACTIVITY_TYPES` includes `"PROGRESS_CHANGED"`, `"AI_SUMMARY_GENERATED"`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_task_schema.py`:

```python
"""The new Jira-like columns exist on the ORM models."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CommunicationTask, TaskActivityLog, TaskComment  # noqa: F401
from app.models.task_collaboration import TASK_ACTIVITY_TYPES


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class TaskSchemaTests(unittest.TestCase):
    def test_new_task_columns_persist(self) -> None:
        with _temp_db() as db:
            t = CommunicationTask(
                title="x", assigned_to_user_id=7, progress_percent=40,
                ai_summary="hi", ai_summary_by="ops",
            )
            db.add(t)
            db.commit()
            db.refresh(t)
            self.assertEqual(t.assigned_to_user_id, 7)
            self.assertEqual(t.progress_percent, 40)
            self.assertEqual(t.ai_summary, "hi")
            self.assertIsNone(t.assigned_at)

    def test_progress_default_zero(self) -> None:
        with _temp_db() as db:
            t = CommunicationTask(title="x")
            db.add(t)
            db.commit()
            db.refresh(t)
            self.assertEqual(t.progress_percent, 0)

    def test_collaboration_actor_id_columns(self) -> None:
        with _temp_db() as db:
            t = CommunicationTask(title="x")
            db.add(t)
            db.commit()
            c = TaskComment(task_id=t.id, comment="c", created_by_id=3)
            a = TaskActivityLog(task_id=t.id, activity_type="PROGRESS_CHANGED", created_by_id=3)
            db.add_all([c, a])
            db.commit()
            self.assertEqual(c.created_by_id, 3)
            self.assertEqual(a.created_by_id, 3)

    def test_activity_vocab_extended(self) -> None:
        self.assertIn("PROGRESS_CHANGED", TASK_ACTIVITY_TYPES)
        self.assertIn("AI_SUMMARY_GENERATED", TASK_ACTIVITY_TYPES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_schema.py -q`
Expected: FAIL (`TypeError: 'assigned_to_user_id' is an invalid keyword argument` / missing vocab).

- [ ] **Step 3: Add columns to `communication_task.py`**

In `backend/app/models/communication_task.py`, in the `# Assignment` block after the `assigned_by` line, add:

```python
    # Real-user assignment (FK is source of truth; `assigned_to` keeps the
    # denormalized display name so cards render without a join).
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime)
```

In the `# Workflow` block, after the `escalation_level` line, add:

```python
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

After the `# Counters` block (after `attachment_count`), add:

```python
    # AI summary (cached; regenerated on demand)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_at: Mapped[datetime | None] = mapped_column(DateTime)
    ai_summary_by: Mapped[str | None] = mapped_column(String(128))
```

(`Text`, `Integer`, `DateTime`, `String`, `ForeignKey` are already imported.)

- [ ] **Step 4: Add columns + vocab to `task_collaboration.py`**

Extend the vocab tuple:

```python
TASK_ACTIVITY_TYPES = (
    "CREATED",
    "STATUS_CHANGED",
    "ASSIGNEE_CHANGED",
    "PRIORITY_CHANGED",
    "DUE_DATE_CHANGED",
    "PROGRESS_CHANGED",
    "COMMENT_ADDED",
    "AI_SUMMARY_GENERATED",
    "ESCALATED",
)
```

In `TaskComment`, after the `created_by` line, add:

```python
    created_by_id: Mapped[int | None] = mapped_column(Integer, index=True)
```

In `TaskActivityLog`, after its `created_by` line, add:

```python
    created_by_id: Mapped[int | None] = mapped_column(Integer, index=True)
```

(`Integer` is already imported in this module.)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_schema.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/communication_task.py backend/app/models/task_collaboration.py backend/tests/test_task_schema.py
git commit -m "feat(tasks): add real-user assignment, progress, AI-summary columns + actor ids"
```

---

## Task 2: Service — actor ids, new activity types, transcript builder

**Files:**
- Modify: `backend/app/services/task_collaboration_service.py`
- Test: `backend/tests/test_task_collaboration.py` (extend)

**Interfaces:**
- Consumes: Task 1 columns.
- Produces:
  - `log_activity(..., created_by_id: int|None = None, ...)`
  - `record_task_changes(db, task, changes, *, created_by=None, created_by_id=None)` — `field_map` now maps `progress_percent → "PROGRESS_CHANGED"`.
  - `add_comment(db, *, task_id, comment, created_by=None, created_by_id=None, commit=True)`
  - `build_transcript(db, task) -> str` — task description + chronological comments + activity, for AI summary.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_task_collaboration.py` (inside the file, new test methods):

```python
class TaskCollabExtrasTests(unittest.TestCase):
    def test_progress_change_logged_with_actor_id(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            entries = collab.record_task_changes(
                db, task, {"progress_percent": (0, 50)}, created_by="ops", created_by_id=9
            )
            db.commit()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].activity_type, "PROGRESS_CHANGED")
            self.assertEqual(entries[0].created_by_id, 9)

    def test_comment_stores_actor_id(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            c = collab.add_comment(
                db, task_id=task.id, comment="hi", created_by="ops", created_by_id=9
            )
            self.assertEqual(c.created_by_id, 9)

    def test_build_transcript_includes_desc_comments_activity(self) -> None:
        with _temp_db() as db:
            task = _make_task(db)
            task.description = "Chase the PO"
            db.commit()
            collab.add_comment(db, task_id=task.id, comment="Called supplier", created_by="ops")
            collab.record_task_changes(db, task, {"status": ("TODO", "IN_PROGRESS")})
            db.commit()
            text = collab.build_transcript(db, task)
            self.assertIn("Chase the PO", text)
            self.assertIn("Called supplier", text)
            self.assertIn("IN_PROGRESS", text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_collaboration.py -q`
Expected: FAIL (`unexpected keyword argument 'created_by_id'` / `build_transcript` missing).

- [ ] **Step 3: Implement service changes**

In `backend/app/services/task_collaboration_service.py`:

Add `created_by_id` param to `log_activity` (signature + row construction):

```python
def log_activity(
    db: Session,
    *,
    task_id: int,
    activity_type: str,
    old_value: Any = None,
    new_value: Any = None,
    created_by: str | None = None,
    created_by_id: int | None = None,
    commit: bool = False,
) -> TaskActivityLog:
    entry = TaskActivityLog(
        task_id=task_id,
        activity_type=activity_type,
        old_value=None if old_value is None else str(old_value)[:500],
        new_value=None if new_value is None else str(new_value)[:500],
        created_by=created_by,
        created_by_id=created_by_id,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry
```

Extend `record_task_changes` (add `progress_percent` to `field_map`, thread `created_by_id`):

```python
def record_task_changes(
    db: Session,
    task: CommunicationTask,
    changes: dict[str, Any],
    *,
    created_by: str | None = None,
    created_by_id: int | None = None,
) -> list[TaskActivityLog]:
    field_map = {
        "status": "STATUS_CHANGED",
        "assigned_to": "ASSIGNEE_CHANGED",
        "assigned_to_user_id": "ASSIGNEE_CHANGED",
        "priority": "PRIORITY_CHANGED",
        "due_date": "DUE_DATE_CHANGED",
        "progress_percent": "PROGRESS_CHANGED",
        "escalation_level": "ESCALATED",
    }
    entries: list[TaskActivityLog] = []
    for field, (old, new) in changes.items():
        activity_type = field_map.get(field)
        if not activity_type or old == new:
            continue
        entries.append(
            log_activity(
                db,
                task_id=task.id,
                activity_type=activity_type,
                old_value=old,
                new_value=new,
                created_by=created_by,
                created_by_id=created_by_id,
            )
        )
    return entries
```

Update `add_comment` to accept + store `created_by_id` (signature, the `TaskComment(...)` row, and the `log_activity(...)` call):

```python
def add_comment(
    db: Session,
    *,
    task_id: int,
    comment: str,
    created_by: str | None = None,
    created_by_id: int | None = None,
    commit: bool = True,
) -> TaskComment:
    task = db.get(CommunicationTask, task_id)
    if task is None:
        raise ValueError("Task not found")
    row = TaskComment(
        task_id=task_id, comment=comment, created_by=created_by, created_by_id=created_by_id
    )
    db.add(row)
    db.flush()
    task.comments_count = (task.comments_count or 0) + 1
    log_activity(
        db,
        task_id=task_id,
        activity_type="COMMENT_ADDED",
        new_value=comment[:120],
        created_by=created_by,
        created_by_id=created_by_id,
    )
    if commit:
        db.commit()
        db.refresh(row)
    return row
```

Add `build_transcript` at the end of the file:

```python
def build_transcript(db: Session, task: CommunicationTask) -> str:
    """Flatten a task's description + comments + activity into a transcript
    suitable for AI summarization (oldest → newest)."""
    lines: list[str] = [f"Task: {task.title}"]
    if task.description:
        lines.append(f"Description: {task.description}")
    for c in list_comments(db, task.id):
        who = c.created_by or "unknown"
        lines.append(f"[comment] {who}: {c.comment}")
    activity = list(reversed(list_activity(db, task.id)))  # list_activity is desc
    for a in activity:
        change = f"{a.old_value or '—'} -> {a.new_value or '—'}"
        lines.append(f"[{a.activity_type}] {a.created_by or 'system'}: {change}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_collaboration.py -q`
Expected: PASS (all, including the 4 originals).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/task_collaboration_service.py backend/tests/test_task_collaboration.py
git commit -m "feat(tasks): actor ids, progress activity, AI transcript builder in collab service"
```

---

## Task 3: Assignee service + endpoint + create/update wiring

**Files:**
- Create: `backend/app/services/task_assignment_service.py`
- Modify: `backend/app/schemas/communication_task.py`
- Modify: `backend/app/routers/communication.py`
- Test: `backend/tests/test_task_assignment.py` (create)

**Interfaces:**
- Consumes: Tasks 1–2; `User` model (`id, full_name, username, email, role, is_active, supplier_id, emp_code`).
- Produces:
  - `task_assignment_service.list_assignees(db) -> list[dict]` → `[{id, label, role, type}]` for active staff+employee.
  - `task_assignment_service.resolve_assignee(db, user_id) -> tuple[User, str]` → `(user, display_name)`; raises `ValueError` if not assignable.
  - `task_assignment_service.display_name(user) -> str`.
  - Schemas: `assigned_to_user_id`, `progress_percent` on Create/Update/Out; `assigned_at`, `ai_summary*` on Out; `watchers: list[int]`.
  - `GET /api/communication/assignees`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_task_assignment.py`:

```python
"""Assignee resolution: staff + employees only, with display name + actor stamp."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CommunicationTask, User  # noqa: F401
from app.services import task_assignment_service as assign


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _user(db, **kw):
    defaults = dict(email=None, username=None, full_name=None, hashed_password="x",
                    role="user", is_active=True, supplier_id=None, emp_code=None)
    defaults.update(kw)
    u = User(**defaults)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


class AssigneeTests(unittest.TestCase):
    def test_list_excludes_suppliers_and_inactive(self) -> None:
        with _temp_db() as db:
            _user(db, email="staff@x.com", full_name="Staff One", role="manager")
            _user(db, username="PRAMOD", full_name="Pramod", role="employee", emp_code="1010")
            _user(db, email="sup@x.com", full_name="Sup", role="supplier", supplier_id=5)
            _user(db, email="off@x.com", full_name="Off", role="user", is_active=False)
            rows = assign.list_assignees(db)
            labels = {r["label"] for r in rows}
            self.assertEqual(labels, {"Staff One", "Pramod"})
            types = {r["label"]: r["type"] for r in rows}
            self.assertEqual(types["Pramod"], "employee")
            self.assertEqual(types["Staff One"], "staff")

    def test_resolve_returns_display_name(self) -> None:
        with _temp_db() as db:
            u = _user(db, email="s@x.com", full_name="Jane Doe", role="user")
            got, name = assign.resolve_assignee(db, u.id)
            self.assertEqual(got.id, u.id)
            self.assertEqual(name, "Jane Doe")

    def test_resolve_rejects_supplier(self) -> None:
        with _temp_db() as db:
            u = _user(db, email="sup@x.com", full_name="Sup", role="supplier", supplier_id=5)
            with self.assertRaises(ValueError):
                assign.resolve_assignee(db, u.id)

    def test_display_name_falls_back(self) -> None:
        with _temp_db() as db:
            u = _user(db, username="PRAMOD", role="employee", emp_code="1010")
            self.assertEqual(assign.display_name(u), "PRAMOD")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_assignment.py -q`
Expected: FAIL (`ModuleNotFoundError: app.services.task_assignment_service`).

- [ ] **Step 3: Create the service**

Create `backend/app/services/task_assignment_service.py`:

```python
"""Resolve task assignees against real user accounts.

Assignable = active staff or employee accounts (suppliers excluded).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.user import User


def display_name(user: User) -> str:
    return user.full_name or user.username or user.email or f"user#{user.id}"


def _account_type(user: User) -> str:
    return "employee" if user.emp_code else "staff"


def list_assignees(db: Session) -> list[dict]:
    rows = db.scalars(
        select(User)
        .where(User.is_active.is_(True), User.supplier_id.is_(None))
        .order_by(User.full_name, User.username)
    ).all()
    return [
        {"id": u.id, "label": display_name(u), "role": u.role, "type": _account_type(u)}
        for u in rows
    ]


def resolve_assignee(db: Session, user_id: int) -> tuple[User, str]:
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.supplier_id is not None:
        raise ValueError("User is not an assignable staff/employee account")
    return user, display_name(user)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_assignment.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Extend schemas**

In `backend/app/schemas/communication_task.py`:

In `CommunicationTaskBase`, change `watchers` and add the two new fields:

```python
    assigned_to: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    assigned_by: Optional[str] = None
    watchers: list[int] = Field(default_factory=list)
    priority: TaskPriority = "P2"
    status: TaskStatus = "TODO"
    signal: TaskSignal = "YELLOW"
    escalation_level: int = 0
    progress_percent: int = Field(default=0, ge=0, le=100)
```

In `CommunicationTaskUpdate`, add:

```python
    assigned_to_user_id: Optional[int] = None
    watchers: Optional[list[int]] = None
    progress_percent: Optional[int] = Field(default=None, ge=0, le=100)
```

In `CommunicationTaskOut`, after `closed_at`, add:

```python
    assigned_at: Optional[datetime] = None
    ai_summary: Optional[str] = None
    ai_summary_at: Optional[datetime] = None
    ai_summary_by: Optional[str] = None
```

- [ ] **Step 6: Add the assignees endpoint + wire create/update**

In `backend/app/routers/communication.py`:

Update imports at the top:

```python
from ..core.deps import get_current_staff
from ..models.user import User
from ..services import task_assignment_service as assign
```

Add the endpoint after `get_task` (before `create_task`):

```python
@router.get("/assignees")
def list_assignees(db: Session = Depends(get_db)):
    """Active staff + employee accounts selectable as task assignees/watchers."""
    return assign.list_assignees(db)
```

Rewrite `create_task` to resolve the assignee + stamp actor:

```python
@router.post("/tasks", response_model=CommunicationTaskOut, status_code=201)
def create_task(
    payload: CommunicationTaskCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    _validate_enum("priority", payload.priority, TASK_PRIORITIES)
    _validate_enum("status", payload.status, TASK_STATUSES)
    _validate_enum("signal", payload.signal, TASK_SIGNALS)
    if payload.task_source:
        _validate_enum("task_source", payload.task_source, TASK_SOURCES)

    data = payload.model_dump()
    if data.get("assigned_to_user_id") is not None:
        try:
            user, name = assign.resolve_assignee(db, data["assigned_to_user_id"])
        except ValueError as e:
            raise HTTPException(422, str(e))
        data["assigned_to"] = name
        data["assigned_at"] = datetime.utcnow()
    data.setdefault("assigned_by", assign.display_name(actor))

    row = CommunicationTask(**data)
    db.add(row)
    db.flush()
    collab.log_activity(
        db,
        task_id=row.id,
        activity_type="CREATED",
        new_value=row.title,
        created_by=assign.display_name(actor),
        created_by_id=actor.id,
    )
    db.commit()
    db.refresh(row)
    return row
```

Rewrite `update_task`'s tracked-change + assignment block (keep enum validation as-is). Replace the body from the `tracked = (...)` line through `db.refresh(row)`:

```python
    actor_name = assign.display_name(actor)

    # Resolve a new assignee (FK → denormalized name + timestamp).
    if "assigned_to_user_id" in data and data["assigned_to_user_id"] is not None:
        try:
            user, name = assign.resolve_assignee(db, data["assigned_to_user_id"])
        except ValueError as e:
            raise HTTPException(422, str(e))
        data["assigned_to"] = name
        data["assigned_at"] = datetime.utcnow()

    # Progress convenience rules.
    if data.get("status") == "DONE":
        data["progress_percent"] = 100
    elif data.get("status") == "BACKLOG":
        data["progress_percent"] = 0

    tracked = (
        "status", "assigned_to_user_id", "priority", "due_date",
        "progress_percent", "escalation_level",
    )
    changes = {
        key: (getattr(row, key), data[key])
        for key in tracked
        if key in data and getattr(row, key) != data[key]
    }

    for key, value in data.items():
        setattr(row, key, value)

    if data.get("status") == "DONE" and not row.closed_at:
        row.closed_at = datetime.utcnow()
    elif "status" in data and data["status"] != "DONE":
        row.closed_at = None

    if changes:
        collab.record_task_changes(
            db, row, changes, created_by=actor_name, created_by_id=actor.id
        )

    db.commit()
    db.refresh(row)
    return row
```

And add `actor: User = Depends(get_current_staff)` to the `update_task` signature:

```python
@router.patch("/tasks/{task_id}", response_model=CommunicationTaskOut)
def update_task(
    task_id: int,
    payload: CommunicationTaskUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
```

Also update the comment endpoint `add_task_comment` to stamp the actor — change its signature and the `collab.add_comment` call:

```python
@tasks_router.post("/{task_id}/comments", status_code=201)
def add_task_comment(
    task_id: int,
    body: dict = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    payload = body or {}
    text = (payload.get("comment") or "").strip()
    if not text:
        raise HTTPException(422, "comment is required")
    try:
        row = collab.add_comment(
            db,
            task_id=task_id,
            comment=text,
            created_by=assign.display_name(actor),
            created_by_id=actor.id,
        )
    except ValueError:
        raise HTTPException(404, "Task not found")
    return _comment_out(row)
```

- [ ] **Step 7: Run the full task test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_assignment.py tests/test_task_collaboration.py tests/test_task_schema.py -q`
Expected: PASS (all).

- [ ] **Step 8: Smoke-import the app to catch wiring errors**

Run: `.venv/Scripts/python.exe -c "import app.main; print('ok')"`
Expected: prints `ok` (no import/typo errors in the router).

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/task_assignment_service.py backend/app/schemas/communication_task.py backend/app/routers/communication.py backend/tests/test_task_assignment.py
git commit -m "feat(tasks): real-user assignee resolution, /assignees endpoint, create/update/comment actor wiring"
```

---

## Task 4: AI summary endpoint

**Files:**
- Modify: `backend/app/routers/communication.py`
- Test: `backend/tests/test_task_ai_summary.py` (create)

**Interfaces:**
- Consumes: `collab.build_transcript` (Task 2); `ai_service.is_enabled()` / `ai_service.summarize_thread()`.
- Produces: `POST /api/tasks/{task_id}/ai-summary` → returns `CommunicationTaskOut`-shaped dict with `ai_summary`, `ai_summary_at`, `ai_summary_by` populated; 503 when LLM disabled; 404 when task missing.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_task_ai_summary.py`:

```python
"""AI summary endpoint behaviour (LLM stubbed)."""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.core.deps import get_current_staff
from app.models import CommunicationTask, User  # noqa: F401
import app.main as main_mod


@contextmanager
def _client():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    task = CommunicationTask(title="Chase PO", description="Need ETA")
    db.add(task)
    db.commit()
    db.refresh(task)

    fake_actor = User(id=1, email="a@x.com", full_name="Admin", hashed_password="x", role="admin")

    def _get_db():
        yield db

    app = main_mod.app
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_staff] = lambda: fake_actor
    try:
        yield TestClient(app), db, task
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


class AiSummaryTests(unittest.TestCase):
    def test_generates_and_caches_summary(self) -> None:
        with _client() as (client, db, task):
            with mock.patch("app.services.ai_service.is_enabled", return_value=True), \
                 mock.patch("app.services.ai_service.summarize_thread", return_value="Short summary."):
                r = client.post(f"/api/tasks/{task.id}/ai-summary")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ai_summary"], "Short summary.")
            self.assertEqual(r.json()["ai_summary_by"], "Admin")

    def test_503_when_llm_disabled(self) -> None:
        with _client() as (client, db, task):
            with mock.patch("app.services.ai_service.is_enabled", return_value=False):
                r = client.post(f"/api/tasks/{task.id}/ai-summary")
            self.assertEqual(r.status_code, 503)

    def test_404_when_task_missing(self) -> None:
        with _client() as (client, db, task):
            with mock.patch("app.services.ai_service.is_enabled", return_value=True):
                r = client.post("/api/tasks/999999/ai-summary")
            self.assertEqual(r.status_code, 404)
```

> Note: the internal routers are mounted with `require_writer_for_writes`. The test overrides `get_current_staff` but the router-level `_rbac` dep still resolves `get_current_user` from a bearer token. Because `app.dependency_overrides` only overrides `get_db` and `get_current_staff`, the `_rbac` guard would 401. To keep this test focused on the endpoint logic, also override the router guard: add `app.dependency_overrides[main_mod.require_writer_for_writes] = lambda: fake_actor` is NOT possible (it's referenced by object). Instead, override `get_current_user`:

Add to the `_client()` overrides block:

```python
    from app.core.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: fake_actor
```

(Place this import + override alongside the other two overrides.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_ai_summary.py -q`
Expected: FAIL (404 for all — endpoint not defined).

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routers/communication.py`, add the import:

```python
from ..services import ai_service
```

Add the endpoint in the comments/activity section (after `task_activity`):

```python
@tasks_router.post("/{task_id}/ai-summary", response_model=CommunicationTaskOut)
def generate_ai_summary(
    task_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
):
    row = db.get(CommunicationTask, task_id)
    if not row:
        raise HTTPException(404, "Task not found")
    if not ai_service.is_enabled():
        raise HTTPException(503, "AI is not enabled")
    transcript = collab.build_transcript(db, row)
    try:
        summary = ai_service.summarize_thread(transcript)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI summary failed: {e}")
    row.ai_summary = (summary or "").strip()
    row.ai_summary_at = datetime.utcnow()
    row.ai_summary_by = assign.display_name(actor)
    collab.log_activity(
        db,
        task_id=row.id,
        activity_type="AI_SUMMARY_GENERATED",
        new_value=row.ai_summary[:120],
        created_by=row.ai_summary_by,
        created_by_id=actor.id,
    )
    db.commit()
    db.refresh(row)
    return row
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_ai_summary.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/communication.py backend/tests/test_task_ai_summary.py
git commit -m "feat(tasks): on-demand AI summary endpoint with caching + activity log"
```

---

## Task 5: Analytics service + dashboard + Excel export endpoints

**Files:**
- Create: `backend/app/services/task_analytics_service.py`
- Modify: `backend/app/routers/communication.py`
- Test: `backend/tests/test_task_analytics.py` (create)

**Interfaces:**
- Consumes: `CommunicationTask`, `TaskActivityLog`.
- Produces:
  - `compute_analytics(db) -> dict` with keys: `totals` (`{total, open, overdue, done, due_today}`), `by_status` (dict), `by_priority` (dict), `by_source` (dict), `by_assignee` (`list[{user_id, name, open, overdue, done}]`), `avg_cycle_hours` (float|None), `throughput` (`list[{date, created, completed}]` — placeholder weekly buckets via Python).
  - `export_workbook(db) -> bytes` — xlsx, sheet 1 "Tasks" (flat rows), sheet 2 "Activity" (raw log).
  - `GET /api/communication/analytics` → the dict.
  - `GET /api/communication/analytics/export` → `StreamingResponse` xlsx.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_task_analytics.py`:

```python
"""Task analytics aggregation + Excel export."""
from __future__ import annotations

import io
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CommunicationTask  # noqa: F401
from app.services import task_analytics_service as analytics


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed(db):
    past = datetime.utcnow() - timedelta(days=2)
    db.add_all([
        CommunicationTask(title="a", status="TODO", priority="P1", task_source="SUPPLIER",
                          assigned_to_user_id=1, assigned_to="Alice", due_date=past),
        CommunicationTask(title="b", status="DONE", priority="P2", task_source="CUSTOMER",
                          assigned_to_user_id=1, assigned_to="Alice", closed_at=datetime.utcnow()),
        CommunicationTask(title="c", status="IN_PROGRESS", priority="P0", task_source="INTERNAL",
                          assigned_to_user_id=2, assigned_to="Bob"),
    ])
    db.commit()


class AnalyticsTests(unittest.TestCase):
    def test_totals_and_breakdowns(self) -> None:
        with _temp_db() as db:
            _seed(db)
            data = analytics.compute_analytics(db)
            self.assertEqual(data["totals"]["total"], 3)
            self.assertEqual(data["totals"]["done"], 1)
            self.assertEqual(data["totals"]["open"], 2)
            self.assertEqual(data["totals"]["overdue"], 1)
            self.assertEqual(data["by_status"]["TODO"], 1)
            self.assertEqual(data["by_priority"]["P0"], 1)
            self.assertEqual(data["by_source"]["CUSTOMER"], 1)

    def test_by_assignee_groups_real_users(self) -> None:
        with _temp_db() as db:
            _seed(db)
            data = analytics.compute_analytics(db)
            by = {r["name"]: r for r in data["by_assignee"]}
            self.assertEqual(by["Alice"]["open"], 1)
            self.assertEqual(by["Alice"]["done"], 1)
            self.assertEqual(by["Bob"]["open"], 1)

    def test_export_workbook_is_valid_xlsx(self) -> None:
        from openpyxl import load_workbook
        with _temp_db() as db:
            _seed(db)
            data = analytics.export_workbook(db)
            wb = load_workbook(io.BytesIO(data))
            self.assertIn("Tasks", wb.sheetnames)
            self.assertIn("Activity", wb.sheetnames)
            ws = wb["Tasks"]
            self.assertEqual(ws.max_row, 4)  # header + 3 tasks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_analytics.py -q`
Expected: FAIL (`ModuleNotFoundError: app.services.task_analytics_service`).

- [ ] **Step 3: Create the analytics service**

Create `backend/app/services/task_analytics_service.py`:

```python
"""Aggregate task metrics + an Excel export, computed from the task table
and the append-only activity log."""
from __future__ import annotations

import io
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.communication_task import CommunicationTask
from ..models.task_collaboration import TaskActivityLog


def compute_analytics(db: Session) -> dict:
    tasks = list(db.scalars(select(CommunicationTask)).all())
    now = datetime.utcnow()
    today = now.date()

    by_status: Counter = Counter()
    by_priority: Counter = Counter()
    by_source: Counter = Counter()
    assignee: dict[int, dict] = {}
    cycle_hours: list[float] = []
    open_count = overdue = done = due_today = 0

    for t in tasks:
        by_status[t.status] += 1
        by_priority[t.priority] += 1
        by_source[t.task_source] += 1
        is_done = t.status == "DONE"
        if is_done:
            done += 1
            if t.closed_at and t.created_at:
                cycle_hours.append((t.closed_at - t.created_at).total_seconds() / 3600.0)
        else:
            open_count += 1
        is_overdue = (not is_done) and t.due_date is not None and t.due_date < now
        if is_overdue:
            overdue += 1
        if (not is_done) and t.due_date is not None and t.due_date.date() == today:
            due_today += 1

        if t.assigned_to_user_id:
            row = assignee.setdefault(
                t.assigned_to_user_id,
                {"user_id": t.assigned_to_user_id, "name": t.assigned_to or f"user#{t.assigned_to_user_id}",
                 "open": 0, "overdue": 0, "done": 0},
            )
            if is_done:
                row["done"] += 1
            else:
                row["open"] += 1
            if is_overdue:
                row["overdue"] += 1

    return {
        "totals": {
            "total": len(tasks), "open": open_count, "overdue": overdue,
            "done": done, "due_today": due_today,
        },
        "by_status": dict(by_status),
        "by_priority": dict(by_priority),
        "by_source": dict(by_source),
        "by_assignee": sorted(assignee.values(), key=lambda r: r["name"].lower()),
        "avg_cycle_hours": round(sum(cycle_hours) / len(cycle_hours), 1) if cycle_hours else None,
        "throughput": _throughput(tasks),
    }


def _throughput(tasks: list[CommunicationTask]) -> list[dict]:
    created: Counter = Counter()
    completed: Counter = Counter()
    for t in tasks:
        if t.created_at:
            created[t.created_at.date().isoformat()] += 1
        if t.status == "DONE" and t.closed_at:
            completed[t.closed_at.date().isoformat()] += 1
    days = sorted(set(created) | set(completed))
    return [{"date": d, "created": created.get(d, 0), "completed": completed.get(d, 0)} for d in days]


_TASK_COLUMNS = (
    "id", "title", "status", "priority", "signal", "task_source",
    "supplier_name", "supplier_po_no", "material_name",
    "assigned_to_user_id", "assigned_to", "progress_percent",
    "comments_count", "escalation_level", "due_date", "closed_at",
    "created_at", "updated_at",
)


def export_workbook(db: Session) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    ws.append(list(_TASK_COLUMNS))
    for t in db.scalars(select(CommunicationTask).order_by(CommunicationTask.id)).all():
        ws.append([_cell(getattr(t, c)) for c in _TASK_COLUMNS])

    ws2 = wb.create_sheet("Activity")
    ws2.append(["id", "task_id", "activity_type", "old_value", "new_value",
                "created_by", "created_by_id", "created_at"])
    for a in db.scalars(select(TaskActivityLog).order_by(TaskActivityLog.id)).all():
        ws2.append([a.id, a.task_id, a.activity_type, a.old_value, a.new_value,
                    a.created_by, a.created_by_id, _cell(a.created_at)])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_analytics.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Add the endpoints**

In `backend/app/routers/communication.py`:

Add imports:

```python
from fastapi.responses import StreamingResponse
from ..services import task_analytics_service as analytics
```

Add endpoints after the `dashboard` endpoint:

```python
@router.get("/analytics")
def task_analytics_summary(db: Session = Depends(get_db)):
    return analytics.compute_analytics(db)


@router.get("/analytics/export")
def task_analytics_export(db: Session = Depends(get_db)):
    data = analytics.export_workbook(db)
    headers = {"Content-Disposition": 'attachment; filename="task-analytics.xlsx"'}
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
```

- [ ] **Step 6: Smoke-import + full backend task suite**

Run: `.venv/Scripts/python.exe -c "import app.main; print('ok')"`
Then: `.venv/Scripts/python.exe -m pytest tests/test_task_analytics.py tests/test_task_assignment.py tests/test_task_collaboration.py tests/test_task_schema.py tests/test_task_ai_summary.py -q`
Expected: `ok`, then all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/task_analytics_service.py backend/app/routers/communication.py backend/tests/test_task_analytics.py
git commit -m "feat(tasks): analytics aggregation + Excel export endpoints"
```

---

## Task 6: Escalation assigns a real user + seed role accounts

**Files:**
- Modify: `backend/app/seed.py`
- Modify: `backend/app/routers/communication_hub.py`
- Test: `backend/tests/test_task_seed_roles.py` (create)

**Interfaces:**
- Consumes: `task_assignment_service`, `User`.
- Produces: `seed.ensure_role_accounts(db) -> dict[str, int]` mapping `{"Purchase Head": <user_id>, "Sourcing Head": <user_id>}`; escalation sets `assigned_to_user_id` from that mapping.

- [ ] **Step 1: Inspect current seed + escalation**

Run:
```bash
grep -n "def run\|def ensure\|SEED_ADMIN\|def _ensure_user\|User(" backend/app/seed.py | head
sed -n '1095,1120p' backend/app/routers/communication_hub.py
```
Expected: see the seed entrypoint (`run`) and the hardcoded `assigned_to="Purchase Head"`, `watchers=["Sourcing Head"]` block.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_task_seed_roles.py`:

```python
"""Seeding the escalation role accounts as real users."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User  # noqa: F401
from app import seed


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class SeedRoleTests(unittest.TestCase):
    def test_ensure_role_accounts_idempotent(self) -> None:
        with _temp_db() as db:
            m1 = seed.ensure_role_accounts(db)
            m2 = seed.ensure_role_accounts(db)
            self.assertEqual(set(m1), {"Purchase Head", "Sourcing Head"})
            self.assertEqual(m1, m2)  # same ids on re-run
            users = db.scalars(select(User).where(User.full_name == "Purchase Head")).all()
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0].role, "manager")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_seed_roles.py -q`
Expected: FAIL (`AttributeError: module 'app.seed' has no attribute 'ensure_role_accounts'`).

- [ ] **Step 4: Implement `ensure_role_accounts` in seed.py**

Add to `backend/app/seed.py` (use the module's existing password hashing import; if `get_password_hash` is already imported use it, otherwise import `from .core.security import get_password_hash`):

```python
_ESCALATION_ROLE_TITLES = ("Purchase Head", "Sourcing Head")


def ensure_role_accounts(db) -> dict[str, int]:
    """Create real manager-role users for the escalation role-titles so
    escalation assigns a real user id. Idempotent (matched by full_name)."""
    from .models.user import User
    from .core.security import get_password_hash

    mapping: dict[str, int] = {}
    for title in _ESCALATION_ROLE_TITLES:
        user = db.scalar(select(User).where(User.full_name == title))
        if user is None:
            slug = title.lower().replace(" ", "")
            user = User(
                email=f"{slug}@internal.local-disabled",
                username=slug,
                full_name=title,
                hashed_password=get_password_hash("disabled-login"),
                role="manager",
                is_active=True,
            )
            db.add(user)
            db.flush()
        mapping[title] = user.id
    db.commit()
    return mapping
```

> Note: `select` must be importable in seed.py — add `from sqlalchemy import select` to its imports if not already present (check with the grep in Step 1). The synthetic email uses a non-routable suffix; these are internal assignment targets, not login accounts (admin renames/activates real people later).

Call it from the seed entrypoint `run(...)` (add a line near where other seeding happens):

```python
    ensure_role_accounts(db)
```

- [ ] **Step 5: Wire escalation to a real user**

In `backend/app/routers/communication_hub.py`, locate the escalation task creation (around the `assigned_to="Purchase Head"` block). Before constructing the task, resolve the role accounts; replace the hardcoded assignment:

```python
    from ..app_imports_placeholder import noop  # DO NOT ADD — illustrative only
```

(Do not add the line above — it's a marker.) Concretely, add near the top imports of `communication_hub.py`:

```python
from .. import seed as seed_mod
```

Then in the escalation handler, replace:

```python
        assigned_to="Purchase Head",
        assigned_by="System",
        watchers=["Sourcing Head"],
```

with:

```python
        assigned_to_user_id=_roles.get("Purchase Head"),
        assigned_to="Purchase Head",
        assigned_by="System",
        watchers=[wid for wid in [_roles.get("Sourcing Head")] if wid],
```

and immediately before that task construction, add:

```python
    _roles = seed_mod.ensure_role_accounts(db)
```

(`ensure_role_accounts` is idempotent and cheap; calling it here guarantees the ids exist even on a fresh DB. If the escalation handler builds the task via a dict/kwargs, set the same keys accordingly.)

- [ ] **Step 6: Run test + smoke import**

Run: `.venv/Scripts/python.exe -m pytest tests/test_task_seed_roles.py -q && .venv/Scripts/python.exe -c "import app.main; print('ok')"`
Expected: PASS, then `ok`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/seed.py backend/app/routers/communication_hub.py backend/tests/test_task_seed_roles.py
git commit -m "feat(tasks): seed escalation role accounts; escalation assigns a real user id"
```

---

## Task 7: One-time remap script for existing dummy assignees

**Files:**
- Create: `backend/scripts/remap_task_assignees.py`

**Interfaces:**
- Consumes: `seed.ensure_role_accounts`, `task_assignment_service.display_name`, models.
- Produces: a CLI guarded by `--yes` that seeds role accounts, back-fills `assigned_to_user_id` by matching `assigned_to`/`watchers` strings to real users (case-insensitive), and prints a before/after report.

> This task has no unit test (it's an operational script run once on the box). Verification is the dry-run output. Keep it idempotent and transactional.

- [ ] **Step 1: Write the script**

Create `backend/scripts/remap_task_assignees.py`:

```python
"""One-time remap of free-text task assignees to real user ids.

Run from backend/ on the Mumbai box:
    .venv/Scripts/python.exe -m scripts.remap_task_assignees          # dry run
    .venv/Scripts/python.exe -m scripts.remap_task_assignees --yes    # apply
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models.communication_task import CommunicationTask
from app.models.user import User
from app import seed
from app.services import task_assignment_service as assign


def _name_index(db) -> dict[str, int]:
    idx: dict[str, int] = {}
    users = db.scalars(
        select(User).where(User.is_active.is_(True), User.supplier_id.is_(None))
    ).all()
    for u in users:
        for key in filter(None, [u.full_name, u.username, u.email]):
            idx[key.strip().lower()] = u.id
    return idx


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        roles = seed.ensure_role_accounts(db)
        print(f"role accounts: {roles}")
        idx = _name_index(db)

        tasks = db.scalars(select(CommunicationTask)).all()
        matched = unmatched = already = 0
        unmatched_names: set[str] = set()

        for t in tasks:
            if t.assigned_to_user_id:
                already += 1
                continue
            name = (t.assigned_to or "").strip().lower()
            uid = idx.get(name)
            if uid:
                if apply:
                    user = db.get(User, uid)
                    t.assigned_to_user_id = uid
                    t.assigned_to = assign.display_name(user)
                matched += 1
            elif name:
                unmatched += 1
                unmatched_names.add(t.assigned_to)

        if apply:
            db.commit()
        print(f"tasks={len(tasks)} already_mapped={already} matched={matched} unmatched={unmatched}")
        if unmatched_names:
            print("unmatched assignee strings (left as-is):")
            for n in sorted(unmatched_names):
                print(f"  - {n}")
        print("APPLIED" if apply else "DRY RUN (pass --yes to apply)")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--yes" in sys.argv)
```

> Confirm `SessionLocal` is the correct exported session factory name in `app/database.py`. If it differs (e.g. `Session`), adjust the import. Check with: `grep -n "SessionLocal\|sessionmaker\|^Session" backend/app/database.py`.

- [ ] **Step 2: Verify it imports (dry-run against local DB is optional)**

Run: `.venv/Scripts/python.exe -c "import scripts.remap_task_assignees; print('ok')"`
Expected: `ok` (no import errors). Actual data run happens on the box during deploy verification.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/remap_task_assignees.py
git commit -m "chore(tasks): one-time remap script for free-text assignees -> real user ids"
```

---

## Task 8: Frontend types + API client

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces TS types: `TaskAssignee`, extended `CommunicationTask` / `CommunicationTaskCreate` / `CommunicationTaskUpdate` (with `assigned_to_user_id`, `watchers: number[]`, `progress_percent`, `ai_summary*`), `TaskAnalytics`; extended `TaskComment`/`TaskActivity` with `created_by_id`.
- Produces API methods: `listAssignees()`, `generateTaskAiSummary(id)`, `taskAnalytics()`, `taskAnalyticsExportUrl()`.

- [ ] **Step 1: Read the current type definitions**

Run:
```bash
sed -n '305,400p' frontend/lib/types.ts
```
Expected: see `TaskComment`, `TaskActivity`, `CommunicationTask`, `CommunicationTaskCreate`, `CommunicationTaskUpdate`.

- [ ] **Step 2: Edit `types.ts`**

In `CommunicationTask` add (keep `assigned_to`):

```ts
  assigned_to_user_id?: number | null;
  assigned_at?: string | null;
  progress_percent?: number;
  ai_summary?: string | null;
  ai_summary_at?: string | null;
  ai_summary_by?: string | null;
```

Change `watchers` on `CommunicationTask` / `CommunicationTaskCreate` / `CommunicationTaskUpdate` to `number[]` (was `string[]`), and add to Create/Update:

```ts
  assigned_to_user_id?: number | null;
  progress_percent?: number;
```

In `TaskComment` and `TaskActivity` add:

```ts
  created_by_id?: number | null;
```

Add new interfaces near the task types:

```ts
export interface TaskAssignee {
  id: number;
  label: string;
  role: string;
  type: "staff" | "employee";
}

export interface TaskAnalytics {
  totals: { total: number; open: number; overdue: number; done: number; due_today: number };
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_source: Record<string, number>;
  by_assignee: { user_id: number; name: string; open: number; overdue: number; done: number }[];
  avg_cycle_hours: number | null;
  throughput: { date: string; created: number; completed: number }[];
}
```

- [ ] **Step 3: Edit `api.ts`**

Add to the imports from `./types`: `TaskAssignee`, `TaskAnalytics`.

In the Task collaboration / Communication Tasks section, add:

```ts
  listAssignees: () => http<TaskAssignee[]>("/api/communication/assignees"),

  generateTaskAiSummary: (taskId: number) =>
    http<CommunicationTask>(`/api/tasks/${taskId}/ai-summary`, { method: "POST" }),

  taskAnalytics: () => http<TaskAnalytics>("/api/communication/analytics"),

  taskAnalyticsExportUrl: () => `/api/communication/analytics/export`,
```

> If `http` prepends the API base URL, the export is a direct browser download — build the full URL the same way other download links in this file do (check for an existing `*ExportUrl`/`download` helper and mirror it; if downloads use `apiBase + path` with the bearer token via fetch+blob, follow that pattern in Task 11 instead of a raw `<a href>`).

- [ ] **Step 4: Type-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds (no TS errors). If `watchers` type change surfaces existing `string[]` usages, fix those call sites to `number[]`.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(tasks-ui): types + api client for assignees, AI summary, analytics"
```

---

## Task 9: Assignee picker + wire into task drawer & create modal

**Files:**
- Create: `frontend/components/tasks/AssigneePicker.tsx`
- Modify: `frontend/app/tasks/page.tsx`

**Interfaces:**
- Consumes: `api.listAssignees()`, `TaskAssignee`.
- Produces: `<AssigneePicker value={number|null} onChange={(id)=>...} assignees={TaskAssignee[]} placeholder?: string />` and a multi-select variant or `multiple` prop for watchers.

- [ ] **Step 1: Create the picker component**

Create `frontend/components/tasks/AssigneePicker.tsx`:

```tsx
"use client";

import { useMemo, useState } from "react";
import type { TaskAssignee } from "@/lib/types";

export function AssigneePicker({
  value,
  onChange,
  assignees,
  placeholder = "Unassigned",
}: {
  value: number | null | undefined;
  onChange: (id: number | null) => void;
  assignees: TaskAssignee[];
  placeholder?: string;
}) {
  return (
    <select
      className="w-full rounded-md border border-brand-border px-2 py-1.5 text-sm"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">{placeholder}</option>
      {assignees.map((a) => (
        <option key={a.id} value={a.id}>
          {a.label} ({a.type === "employee" ? "emp" : a.role})
        </option>
      ))}
    </select>
  );
}

export function WatcherPicker({
  value,
  onChange,
  assignees,
}: {
  value: number[];
  onChange: (ids: number[]) => void;
  assignees: TaskAssignee[];
}) {
  const [open, setOpen] = useState(false);
  const selected = useMemo(() => new Set(value), [value]);
  const toggle = (id: number) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    onChange([...next]);
  };
  const labels = assignees.filter((a) => selected.has(a.id)).map((a) => a.label);
  return (
    <div className="relative">
      <button
        type="button"
        className="w-full rounded-md border border-brand-border px-2 py-1.5 text-left text-sm"
        onClick={() => setOpen((o) => !o)}
      >
        {labels.length ? labels.join(", ") : "No watchers"}
      </button>
      {open && (
        <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-brand-border bg-white shadow">
          {assignees.map((a) => (
            <label key={a.id} className="flex items-center gap-2 px-2 py-1 text-sm hover:bg-gray-50">
              <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)} />
              {a.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Load assignees in the tasks page**

In `frontend/app/tasks/page.tsx`, add state + fetch near the other top-level data loads:

```tsx
import { AssigneePicker, WatcherPicker } from "@/components/tasks/AssigneePicker";
import type { TaskAssignee } from "@/lib/types";

// inside the component:
const [assignees, setAssignees] = useState<TaskAssignee[]>([]);
useEffect(() => {
  api.listAssignees().then(setAssignees).catch(() => setAssignees([]));
}, []);
```

- [ ] **Step 3: Replace the drawer's free-text assignee input**

In the `TaskDrawer` component (the assignee `<input>` around the "Assignee" field), replace the text input with:

```tsx
<AssigneePicker
  value={task.assigned_to_user_id ?? null}
  assignees={assignees}
  onChange={(id) => onUpdate({ assigned_to_user_id: id })}
/>
```

(Use the drawer's existing update callback — the one that calls `api.updateTask`. If it's named differently, pass `{ assigned_to_user_id: id }` to it.)

- [ ] **Step 4: Replace the create-modal assignee field**

In `CreateTaskModal`, replace the free-text assignee input with `<AssigneePicker>` bound to a local `assignedToUserId` state, and include `assigned_to_user_id: assignedToUserId` in the `api.createTask(...)` payload.

- [ ] **Step 5: Pass `assignees` into both child components**

Ensure `TaskDrawer` and `CreateTaskModal` receive `assignees` as a prop from the page (add it to their prop types and the JSX where they're rendered).

- [ ] **Step 6: Type-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds. Resolve any prop-type mismatches.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/tasks/AssigneePicker.tsx frontend/app/tasks/page.tsx
git commit -m "feat(tasks-ui): real-user assignee + watcher pickers in drawer and create modal"
```

---

## Task 10: Progress bar, AI summary panel, unified timeline

**Files:**
- Modify: `frontend/app/tasks/page.tsx`

**Interfaces:**
- Consumes: `api.generateTaskAiSummary`, `api.listTaskComments`, `api.listTaskActivity`, task fields `progress_percent`, `ai_summary*`.

- [ ] **Step 1: Add a progress bar to Kanban cards**

In the card renderer, below the title/badges row, add:

```tsx
<div className="mt-2 h-1.5 w-full rounded-full bg-gray-100">
  <div
    className="h-1.5 rounded-full bg-emerald-500"
    style={{ width: `${task.progress_percent ?? 0}%` }}
  />
</div>
```

- [ ] **Step 2: Add a progress control in the drawer**

Below the status/priority controls, add a range input:

```tsx
<div>
  <label className="text-xs font-medium text-brand-muted">Progress: {task.progress_percent ?? 0}%</label>
  <input
    type="range" min={0} max={100} step={5}
    value={task.progress_percent ?? 0}
    onChange={(e) => onUpdate({ progress_percent: Number(e.target.value) })}
    className="w-full"
  />
</div>
```

- [ ] **Step 3: Add the AI summary panel at the top of the drawer**

```tsx
<div className="rounded-md border border-brand-border bg-slate-50 p-3">
  <div className="flex items-center justify-between">
    <span className="text-xs font-semibold text-brand-dark">AI Summary</span>
    <button
      className="text-xs text-brand-primary disabled:opacity-50"
      disabled={summarizing}
      onClick={async () => {
        setSummarizing(true);
        try {
          const updated = await api.generateTaskAiSummary(task.id);
          onSummary(updated); // parent merges ai_summary fields into the task
        } catch (e) {
          alert("AI summary unavailable (LLM may be disabled).");
        } finally {
          setSummarizing(false);
        }
      }}
    >
      {task.ai_summary ? "Regenerate" : "Summarize"}
    </button>
  </div>
  <p className="mt-1 text-xs text-brand-muted">
    {task.ai_summary || "No summary yet."}
  </p>
  {task.ai_summary_at && (
    <p className="mt-1 text-[10px] text-brand-muted">
      by {task.ai_summary_by} · {new Date(task.ai_summary_at).toLocaleString()}
    </p>
  )}
</div>
```

Add `const [summarizing, setSummarizing] = useState(false);` in `TaskDrawer`, and an `onSummary` prop the page uses to update its task list/selected task.

- [ ] **Step 4: Merge comments + activity into one timeline**

In the drawer, replace the separate Comments/Activity tabs (or augment) with a merged, newest-first feed. Add a helper inside the drawer:

```tsx
type FeedItem = { kind: "comment" | "activity"; at: string; who: string | null; text: string };

const feed: FeedItem[] = [
  ...comments.map((c) => ({
    kind: "comment" as const, at: c.created_at, who: c.created_by, text: c.comment,
  })),
  ...activity.map((a) => ({
    kind: "activity" as const, at: a.created_at, who: a.created_by,
    text: `${a.activity_type.replace(/_/g, " ").toLowerCase()}${
      a.new_value ? `: ${a.old_value ? `${a.old_value} → ` : ""}${a.new_value}` : ""
    }`,
  })),
].sort((x, y) => +new Date(y.at) - +new Date(x.at));
```

Render `feed` as a vertical list, distinguishing comments (rounded card) from activity (muted single line). Keep the existing "Add a comment" input + Send (it already posts via `api.addTaskComment`).

- [ ] **Step 5: Type-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/tasks/page.tsx
git commit -m "feat(tasks-ui): progress bar, AI summary panel, unified activity timeline"
```

---

## Task 11: Analytics page + export + sidebar link

**Files:**
- Create: `frontend/app/tasks/analytics/page.tsx`
- Modify: `frontend/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: `api.taskAnalytics()`, `api.taskAnalyticsExportUrl()`.

- [ ] **Step 1: Inspect existing download + sidebar patterns**

Run:
```bash
grep -n "ExportUrl\|download\|blob\|a href\|saveAs" frontend/lib/api.ts frontend/app/tasks/page.tsx | head
sed -n '1,80p' frontend/components/layout/Sidebar.tsx
```
Expected: see how existing exports trigger a download and how sidebar items are declared (icon + href + role gate).

- [ ] **Step 2: Create the analytics page**

Create `frontend/app/tasks/analytics/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import type { TaskAnalytics } from "@/lib/types";

export default function TaskAnalyticsPage() {
  const [data, setData] = useState<TaskAnalytics | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.taskAnalytics().then(setData).catch((e) => setErr((e as Error).message));
  }, []);

  const download = async () => {
    // Mirror the existing authed-download pattern in this app (fetch + blob).
    const res = await fetch(api.taskAnalyticsExportUrl(), {
      headers: { Authorization: `Bearer ${localStorage.getItem("token") ?? ""}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "task-analytics.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (err) return <div className="p-6 text-signal-red">{err}</div>;
  if (!data) return <div className="p-6 text-brand-muted">Loading…</div>;

  const Stat = ({ label, value }: { label: string; value: number | string }) => (
    <div className="rounded-lg border border-brand-border p-4">
      <div className="text-2xl font-semibold text-brand-dark">{value}</div>
      <div className="text-xs text-brand-muted">{label}</div>
    </div>
  );

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-brand-dark">Task Analytics</h1>
        <button className="btn-primary" onClick={download}>Export Excel</button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Stat label="Total" value={data.totals.total} />
        <Stat label="Open" value={data.totals.open} />
        <Stat label="Overdue" value={data.totals.overdue} />
        <Stat label="Done" value={data.totals.done} />
        <Stat label="Avg cycle (h)" value={data.avg_cycle_hours ?? "—"} />
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-brand-dark">Workload by assignee</h2>
        <div className="overflow-x-auto rounded-lg border border-brand-border">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-brand-muted">
              <tr><th className="p-2">Assignee</th><th className="p-2">Open</th><th className="p-2">Overdue</th><th className="p-2">Done</th></tr>
            </thead>
            <tbody>
              {data.by_assignee.map((r) => (
                <tr key={r.user_id} className="border-t border-brand-border">
                  <td className="p-2">{r.name}</td>
                  <td className="p-2">{r.open}</td>
                  <td className="p-2 text-signal-red">{r.overdue}</td>
                  <td className="p-2">{r.done}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-6 sm:grid-cols-3">
        {(["by_status", "by_priority", "by_source"] as const).map((key) => (
          <section key={key}>
            <h2 className="mb-2 text-sm font-semibold capitalize text-brand-dark">
              {key.replace("by_", "By ")}
            </h2>
            <div className="space-y-1">
              {Object.entries(data[key]).map(([k, v]) => (
                <div key={k} className="flex justify-between text-sm">
                  <span className="text-brand-muted">{k}</span>
                  <span className="font-medium text-brand-dark">{v}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
```

> In Step 1 you confirmed the real authed-download pattern and token storage key. If this app stores the JWT somewhere other than `localStorage.token` (e.g. a Zustand store or cookie), use that exact source instead of `localStorage.getItem("token")`.

- [ ] **Step 3: Add the sidebar link**

In `frontend/components/layout/Sidebar.tsx`, add a nav entry for staff (mirror an existing item's shape), pointing to `/tasks/analytics` with a chart icon (e.g. `BarChart3` from lucide-react), gated to staff (not portal accounts) like the other internal links.

- [ ] **Step 4: Type-check via build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/tasks/analytics/page.tsx frontend/components/layout/Sidebar.tsx
git commit -m "feat(tasks-ui): task analytics dashboard page + Excel export + sidebar link"
```

---

## Task 12: Full verification + deploy

**Files:** none (verification only).

- [ ] **Step 1: Run the entire backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass (existing + the 5 new task test files).

- [ ] **Step 2: Backend app boots + schema evolves on a scratch SQLite DB**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -c "import app.main; print('import ok')"
```
Expected: `import ok`. (Boot on the box will run `schema_evolve.ensure_columns`, adding the new columns — confirmed in Step 5 below via logs.)

- [ ] **Step 3: Frontend production build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 4: Push to deploy (requires explicit user authorization)**

```bash
git push origin main
```
Then watch GitHub Actions to green and `/healthz` to 200.

- [ ] **Step 5: On the Mumbai box — confirm schema + run the remap**

After deploy, on the box (`backend/` venv against the pooler):
```bash
.venv/Scripts/python.exe -m scripts.remap_task_assignees        # dry run, review report
.venv/Scripts/python.exe -m scripts.remap_task_assignees --yes  # apply
```
Expected: role accounts created, existing tasks back-filled, unmatched strings listed. Verify `/api/communication/assignees` returns staff + employees, the analytics page renders, and an escalation creates a task with a real `assigned_to_user_id`.

- [ ] **Step 6: Final commit (if any verification fixups were needed)**

```bash
git add -A -- backend frontend   # NEVER stage docs/Hariom Employee details.xlsx (gitignored)
git commit -m "fix(tasks): verification fixups"
```

---

## Self-Review

**Spec coverage:**
- Real-user assignment (staff+employees) → Tasks 1, 3, 9. ✓
- Remap existing dummy data → Tasks 6 (seed) + 7 (script) + 12 (run on box). ✓
- Comments with real author → Tasks 1, 2, 3 (actor stamped). ✓
- Manual progress % (+ DONE→100/BACKLOG→0) → Tasks 1, 3, 10. ✓
- Unified activity timeline (extended vocab) → Tasks 1, 2, 10. ✓
- AI summary (cached, on-demand, 503 when off) → Tasks 1, 2, 4, 10. ✓
- Analytics dashboard + Excel export → Tasks 5, 8, 11. ✓
- "Log everything" via existing append-only `task_activity_logs` (extended) → Tasks 1, 2, 5. ✓
- Suppliers excluded from assignees/analytics → Task 3 service filter + staff-only routers. ✓

**Placeholder scan:** No "TBD"/"implement later". The two `> Note`/marker lines in Tasks 5 and 6 explicitly say not to copy them and point to a `grep` to confirm a name (`SessionLocal`, `select` import) before implementing — these are verification prompts, not placeholders. Frontend download/token Steps direct the implementer to mirror the app's existing authed-download pattern confirmed via grep, rather than guessing.

**Type consistency:** `assigned_to_user_id: int|None` consistent across model/schema/service/router/TS. `watchers: list[int]` (backend) ↔ `number[]` (TS). `display_name()` used uniformly for the denormalized name and actor labels. `build_transcript`, `compute_analytics`, `export_workbook`, `list_assignees`, `resolve_assignee` names match between definition (Tasks 2/3/5) and use (Tasks 4/5/router). Activity vocab additions (`PROGRESS_CHANGED`, `AI_SUMMARY_GENERATED`) defined in Task 1 and emitted in Tasks 2/4.
