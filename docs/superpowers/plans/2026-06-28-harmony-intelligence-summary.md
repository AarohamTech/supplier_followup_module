# Harmony Intelligence Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily scheduled worker that emails a branded "Harmony Intelligence Summary" (counts, most-critical POs, heated conversations, AI summary, top delay-risk, overdue) to a configurable recipient list, fully customizable from the admin Settings page.

**Architecture:** A new interval-ticker scheduler job (`admin_digest_cron`) reuses the existing `EngineJobSpec` registry. Its runner calls `admin_digest_service.send_digest_if_due(db)`, which reads config from a new `AppSetting` key `admin_digest`, gates to one send per local calendar day on/after the configured hour, builds HTML via the existing `brand_email` helpers, and sends through a new public `mail_send_worker.send_html_email`. Config is exposed via `/api/settings/admin-digest` (GET/PUT/test) and edited in a new "Daily Summary" card on the Settings page.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`select`), APScheduler, Python 3.13 (`zoneinfo`), Next.js/React/TypeScript frontend, `unittest` + `unittest.mock` for tests (no DB fixtures — sessions are mocked).

## Global Constraints

- Backend lives under `backend/app`; tests under `backend/tests`, run with `python -m pytest` from `backend/` using the project venv at `backend/.venv` (python is not on PATH — invoke via the venv).
- Tests use `unittest.TestCase` + `MagicMock`/`patch`, mocking the DB session (no live DB). Match the style of `backend/tests/test_po_followup_mail_service.py`.
- Email HTML is inline-styles only (Gmail/Outlook/Apple Mail safe). Reuse `brand_email.header_html` / `shell` / `footer_html`. No emoji, no icons. Brand red is `#E11D2E`. Title is exactly **"Harmony Intelligence Summary"**.
- The committed reference mock `backend/app/services/templates/digest_sample.html` is the canonical visual target for section markup.
- Config defaults: `enabled=false`, empty `recipients`, `send_hour=9`, `timezone="Asia/Kolkata"`, all sections on. `last_sent_date` is service-written, never user-edited.
- Settings write endpoints are guarded by `Depends(require_manager)` (the existing `_MGR` list in `settings.py`).
- Commit after each task with the shown message.

---

### Task 1: Config schema in `settings_service`

**Files:**
- Modify: `backend/app/services/settings_service.py`
- Test: `backend/tests/test_admin_digest_settings.py`

**Interfaces:**
- Consumes: existing `_get_raw(db, key)`, `_set_raw(db, key, value)` in `settings_service.py`.
- Produces:
  - `ADMIN_DIGEST_KEY: str = "admin_digest"`
  - `DEFAULT_ADMIN_DIGEST: dict` (the full default config below)
  - `get_admin_digest(db: Session) -> dict` — returns a complete config dict (stored values merged over defaults; always has every key).
  - `set_admin_digest(db: Session, values: dict) -> dict` — validates/sanitizes a partial update, persists, returns the full merged config via `get_admin_digest`.
  - `mark_admin_digest_sent(db: Session, day_iso: str) -> None` — writes `last_sent_date` only.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_digest_settings.py`:

```python
import unittest
from unittest.mock import MagicMock

from app.services import settings_service as svc


class AdminDigestSettingsTests(unittest.TestCase):
    def _db_with(self, stored):
        """A MagicMock db whose AppSetting row .value is `stored` (or None)."""
        db = MagicMock()
        row = None if stored is None else MagicMock(value=dict(stored))
        db.get.return_value = row
        return db, row

    def test_get_returns_full_defaults_when_unset(self):
        db, _ = self._db_with(None)
        cfg = svc.get_admin_digest(db)
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["recipients"], [])
        self.assertEqual(cfg["send_hour"], 9)
        self.assertEqual(cfg["timezone"], "Asia/Kolkata")
        self.assertTrue(cfg["sections"]["critical"])
        self.assertEqual(cfg["limits"]["critical"], 10)
        self.assertIsNone(cfg["last_sent_date"])

    def test_get_merges_stored_over_defaults(self):
        db, _ = self._db_with({"enabled": True, "recipients": ["a@x.com"], "send_hour": 7})
        cfg = svc.get_admin_digest(db)
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["recipients"], ["a@x.com"])
        self.assertEqual(cfg["send_hour"], 7)
        # untouched keys still defaulted
        self.assertTrue(cfg["sections"]["overdue"])

    def test_set_sanitizes_and_clamps(self):
        db, _ = self._db_with(None)
        out = svc.set_admin_digest(db, {
            "send_hour": 99, "recipients": ["a@x.com", "bad", "b@y.com", 5],
            "limits": {"critical": -3, "heated": 4},
        })
        self.assertEqual(out["send_hour"], 23)          # clamped 0..23
        self.assertEqual(out["recipients"], ["a@x.com", "b@y.com"])  # invalid dropped
        self.assertEqual(out["limits"]["critical"], 1)  # min 1
        self.assertEqual(out["limits"]["heated"], 4)
        db.commit.assert_called_once()

    def test_mark_sent_writes_only_last_sent_date(self):
        db, _ = self._db_with({"enabled": True})
        svc.mark_admin_digest_sent(db, "2026-06-27")
        cfg = svc.get_admin_digest(db)
        self.assertEqual(cfg["last_sent_date"], "2026-06-27")
        db.commit.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_settings.py -v` (from `backend/`)
Expected: FAIL — `AttributeError: module 'app.services.settings_service' has no attribute 'get_admin_digest'`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/services/settings_service.py`:

```python
import re

ADMIN_DIGEST_KEY = "admin_digest"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_ADMIN_DIGEST: dict[str, Any] = {
    "enabled": False,
    "recipients": [],
    "send_hour": 9,
    "timezone": "Asia/Kolkata",
    "sections": {
        "counts": True, "summary": True, "critical": True,
        "heated": True, "risk": True, "overdue": True,
    },
    "limits": {"critical": 10, "heated": 5, "risk": 10, "overdue": 15},
    "last_sent_date": None,
}


def get_admin_digest(db: Session) -> dict[str, Any]:
    stored = _get_raw(db, ADMIN_DIGEST_KEY) or {}
    cfg = {
        "enabled": bool(stored.get("enabled", DEFAULT_ADMIN_DIGEST["enabled"])),
        "recipients": [e for e in stored.get("recipients", []) if isinstance(e, str)],
        "send_hour": _clamp_int(stored.get("send_hour"), DEFAULT_ADMIN_DIGEST["send_hour"], 0, 23),
        "timezone": str(stored.get("timezone") or DEFAULT_ADMIN_DIGEST["timezone"]),
        "sections": {**DEFAULT_ADMIN_DIGEST["sections"], **_bool_map(stored.get("sections"))},
        "limits": {**DEFAULT_ADMIN_DIGEST["limits"], **_int_map(stored.get("limits"), lo=1, hi=100)},
        "last_sent_date": stored.get("last_sent_date") or None,
    }
    return cfg


def set_admin_digest(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    existing = _get_raw(db, ADMIN_DIGEST_KEY) or {}
    if "enabled" in values:
        existing["enabled"] = bool(values["enabled"])
    if "recipients" in values:
        existing["recipients"] = [
            e.strip() for e in values["recipients"]
            if isinstance(e, str) and _EMAIL_RE.match(e.strip())
        ]
    if "send_hour" in values:
        existing["send_hour"] = _clamp_int(values["send_hour"], DEFAULT_ADMIN_DIGEST["send_hour"], 0, 23)
    if "timezone" in values and values["timezone"]:
        existing["timezone"] = str(values["timezone"])
    if "sections" in values:
        existing["sections"] = {**existing.get("sections", {}), **_bool_map(values["sections"])}
    if "limits" in values:
        existing["limits"] = {**existing.get("limits", {}), **_int_map(values["limits"], lo=1, hi=100)}
    _set_raw(db, ADMIN_DIGEST_KEY, existing)
    db.commit()
    return get_admin_digest(db)


def mark_admin_digest_sent(db: Session, day_iso: str) -> None:
    existing = _get_raw(db, ADMIN_DIGEST_KEY) or {}
    existing["last_sent_date"] = day_iso
    _set_raw(db, ADMIN_DIGEST_KEY, existing)
    db.commit()


def _clamp_int(raw: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(raw)))
    except (TypeError, ValueError):
        return default


def _bool_map(raw: Any) -> dict[str, bool]:
    return {str(k): bool(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _int_map(raw: Any, *, lo: int, hi: int) -> dict[str, int]:
    out: dict[str, int] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[str(k)] = max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                continue
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_settings.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/settings_service.py backend/tests/test_admin_digest_settings.py
git commit -m "feat(digest): admin_digest config getter/setter in settings_service"
```

---

### Task 2: Public HTML send helper in `mail_send_worker`

**Files:**
- Modify: `backend/app/workers/mail_send_worker.py`
- Test: `backend/tests/test_send_html_email.py`

**Interfaces:**
- Consumes: existing `_config_ready() -> tuple[bool, str]`, `_open_client()`, `_send_one(em)`, `_html_to_text(html)` in `mail_send_worker.py`.
- Produces: `send_html_email(to_emails: list[str], subject: str, html: str, *, text: str | None = None) -> dict` returning `{"sent": bool, "recipients": int, "reason": str}`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_send_html_email.py`:

```python
import unittest
from unittest.mock import patch

from app.workers import mail_send_worker as w


class SendHtmlEmailTests(unittest.TestCase):
    def test_skips_when_smtp_not_ready(self):
        with patch.object(w, "_config_ready", return_value=(False, "SMTP_ENABLED is false")):
            result = w.send_html_email(["a@x.com"], "Subj", "<b>hi</b>")
        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "SMTP_ENABLED is false")

    def test_skips_when_no_recipients(self):
        with patch.object(w, "_config_ready", return_value=(True, "")):
            result = w.send_html_email([], "Subj", "<b>hi</b>")
        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "no recipients")

    def test_sends_html_alternative(self):
        with patch.object(w, "_config_ready", return_value=(True, "")), \
             patch.object(w, "_send_one") as send_one:
            result = w.send_html_email(["a@x.com", "b@y.com"], "Subj", "<b>hi</b>")
        self.assertTrue(result["sent"])
        self.assertEqual(result["recipients"], 2)
        em = send_one.call_args.args[0]
        self.assertEqual(em["Subject"], "Subj")
        self.assertEqual(em["To"], "a@x.com, b@y.com")
        self.assertTrue(em.get_content_type().startswith("multipart"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_send_html_email.py -v`
Expected: FAIL — `AttributeError: module 'app.workers.mail_send_worker' has no attribute 'send_html_email'`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/workers/mail_send_worker.py` (after `_send_one`):

```python
def send_html_email(
    to_emails: list[str],
    subject: str,
    html: str,
    *,
    text: str | None = None,
) -> dict:
    """Send a standalone branded HTML email (not tied to a CommunicationMessage).

    Used by the admin digest. Returns a status dict; never raises on SMTP-disabled.
    """
    ok, reason = _config_ready()
    if not ok:
        return {"sent": False, "recipients": 0, "reason": reason}
    recipients = [e for e in (to_emails or []) if e]
    if not recipients:
        return {"sent": False, "recipients": 0, "reason": "no recipients"}

    em = EmailMessage()
    em["From"] = settings.SMTP_FROM
    em["To"] = ", ".join(recipients)
    em["Subject"] = subject or "(no subject)"
    em.set_content(text or _html_to_text(html) or "")
    em.add_alternative(html, subtype="html")
    _send_one(em)
    return {"sent": True, "recipients": len(recipients), "reason": ""}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_send_html_email.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/mail_send_worker.py backend/tests/test_send_html_email.py
git commit -m "feat(digest): public send_html_email helper for standalone branded mail"
```

---

### Task 3: Digest data gathering (counts, critical, risk, overdue)

**Files:**
- Create: `backend/app/services/admin_digest_service.py`
- Test: `backend/tests/test_admin_digest_gather.py`

**Interfaces:**
- Consumes: `ProcurementRecord` (`backend/app/models/procurement.py`), `CommunicationMessage` (`backend/app/models/communication_message.py`), SQLAlchemy `select`/`func`.
- Produces (pure formatters tested directly; thin DB wrappers fetch then format):
  - `summarize_counts(active_rows, overdue_count, critical_count, new_replies) -> dict`
  - `format_critical(rows, today) -> list[dict]`
  - `format_overdue(rows, today) -> list[dict]`
  - `format_risk(rows) -> list[dict]`
  - `_days_late(shipment_date, today) -> int | None`
  - `_gather_counts(db) -> dict`, `_gather_critical(db, limit) -> list[dict]`,
    `_gather_risk(db, limit) -> list[dict]`, `_gather_overdue(db, limit) -> list[dict]`
- Data shapes: a critical item is `{"po","supplier","material","signal","days_late","risk"}`; overdue `{"po","supplier","shipment","status"}`; risk `{"po","supplier","reason","score"}`; counts `{"active","open_followups","overdue","critical","new_replies","signals":{GREEN,YELLOW,RED,BLACK}}`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_digest_gather.py`:

```python
import unittest
from datetime import datetime
from types import SimpleNamespace

from app.services import admin_digest_service as svc

TODAY = datetime(2026, 6, 27)


def rec(**kw):
    base = dict(supplier_po_no="PO-1", supplier_name="Acme", material_name="Bolt",
                signal="RED", escalation_level="LEVEL_1", risk_score=70,
                risk_band="HIGH", risk_reason="overdue", shipment_date=datetime(2026, 6, 20),
                followup_status="URGENT_FOLLOWUP")
    base.update(kw)
    return SimpleNamespace(**base)


class GatherFormatTests(unittest.TestCase):
    def test_days_late_positive_and_none(self):
        self.assertEqual(svc._days_late(datetime(2026, 6, 20), TODAY), 7)
        self.assertIsNone(svc._days_late(None, TODAY))
        self.assertEqual(svc._days_late(datetime(2026, 6, 30), TODAY), 0)  # future -> 0, not negative

    def test_format_critical_shapes_and_orders_fields(self):
        rows = [rec(supplier_po_no="PO-9", signal="BLACK", risk_score=96,
                    shipment_date=datetime(2026, 6, 8))]
        out = svc.format_critical(rows, TODAY)
        self.assertEqual(out[0]["po"], "PO-9")
        self.assertEqual(out[0]["signal"], "Black")     # title-cased label
        self.assertEqual(out[0]["days_late"], 19)
        self.assertEqual(out[0]["risk"], 96)

    def test_format_overdue_labels_due_today_vs_overdue(self):
        rows = [rec(supplier_po_no="A", shipment_date=datetime(2026, 6, 27)),
                rec(supplier_po_no="B", shipment_date=datetime(2026, 6, 20))]
        out = svc.format_overdue(rows, TODAY)
        self.assertEqual(out[0]["status"], "Due today")
        self.assertEqual(out[1]["status"], "Overdue")

    def test_summarize_counts_builds_signal_map(self):
        active = [rec(signal="GREEN"), rec(signal="GREEN"), rec(signal="BLACK"), rec(signal=None)]
        counts = svc.summarize_counts(active, overdue_count=3, critical_count=1, new_replies=5)
        self.assertEqual(counts["active"], 4)
        self.assertEqual(counts["signals"]["GREEN"], 2)
        self.assertEqual(counts["signals"]["BLACK"], 1)
        self.assertEqual(counts["overdue"], 3)
        self.assertEqual(counts["new_replies"], 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_gather.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.admin_digest_service'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/admin_digest_service.py`:

```python
"""Harmony Intelligence Summary — daily admin digest.

Gathers current procurement state, renders a branded HTML email, and sends it
once per local calendar day to an admin-configured recipient list. All config
lives in AppSetting key `admin_digest` (see settings_service).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..models.communication_message import CommunicationMessage
from ..models.procurement import ProcurementRecord

log = logging.getLogger(__name__)

CRITICAL_ESCALATIONS = ("CRITICAL", "LEVEL_2")
OPEN_FOLLOWUP_STATUSES = (
    "REMINDER_DUE", "URGENT_FOLLOWUP", "STRONG_FOLLOWUP",
    "AI_FOLLOWUP", "CRITICAL_ESCALATION", "PENDING_ACK",
)


def _days_late(shipment_date: datetime | None, today: datetime) -> int | None:
    if shipment_date is None:
        return None
    delta = (today.date() - shipment_date.date()).days
    return delta if delta > 0 else 0


def _po(r: Any) -> str:
    return r.supplier_po_no or "—"


def summarize_counts(active_rows, overdue_count, critical_count, new_replies) -> dict:
    signals = {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}
    open_followups = 0
    for r in active_rows:
        if r.signal in signals:
            signals[r.signal] += 1
        if getattr(r, "followup_status", None) in OPEN_FOLLOWUP_STATUSES:
            open_followups += 1
    return {
        "active": len(active_rows),
        "open_followups": open_followups,
        "overdue": overdue_count,
        "critical": critical_count,
        "new_replies": new_replies,
        "signals": signals,
    }


def format_critical(rows, today) -> list[dict]:
    return [{
        "po": _po(r), "supplier": r.supplier_name or "—", "material": r.material_name or "",
        "signal": (r.signal or "").title(), "days_late": _days_late(r.shipment_date, today),
        "risk": r.risk_score,
    } for r in rows]


def format_overdue(rows, today) -> list[dict]:
    out = []
    for r in rows:
        late = _days_late(r.shipment_date, today)
        status = "Due today" if late == 0 else "Overdue"
        ship = r.shipment_date.strftime("%d %b") if r.shipment_date else "—"
        out.append({"po": _po(r), "supplier": r.supplier_name or "—",
                    "shipment": ship, "status": status, "days_late": late})
    return out


def format_risk(rows) -> list[dict]:
    return [{"po": _po(r), "supplier": r.supplier_name or "—",
             "reason": r.risk_reason or "", "score": r.risk_score or 0} for r in rows]


def _gather_counts(db: Session) -> dict:
    today = datetime.utcnow()
    active = list(db.scalars(select(ProcurementRecord)).all())
    overdue = sum(1 for r in active if r.shipment_date and r.shipment_date.date() <= today.date())
    critical = sum(1 for r in active
                   if r.signal == "BLACK" or r.escalation_level in CRITICAL_ESCALATIONS)
    since = today - timedelta(hours=24)
    new_replies = db.scalar(
        select(func.count()).select_from(CommunicationMessage).where(
            CommunicationMessage.direction == "INCOMING",
            CommunicationMessage.received_at >= since,
        )
    ) or 0
    return summarize_counts(active, overdue, critical, new_replies)


def _gather_critical(db: Session, limit: int) -> list[dict]:
    rows = db.scalars(
        select(ProcurementRecord)
        .where(or_(ProcurementRecord.signal == "BLACK",
                   ProcurementRecord.escalation_level.in_(CRITICAL_ESCALATIONS)))
        .order_by(ProcurementRecord.risk_score.desc().nullslast())
        .limit(limit)
    ).all()
    return format_critical(rows, datetime.utcnow())


def _gather_risk(db: Session, limit: int) -> list[dict]:
    rows = db.scalars(
        select(ProcurementRecord)
        .where(ProcurementRecord.risk_band == "HIGH")
        .order_by(ProcurementRecord.risk_score.desc().nullslast())
        .limit(limit)
    ).all()
    return format_risk(rows)


def _gather_overdue(db: Session, limit: int) -> list[dict]:
    today = datetime.utcnow()
    rows = db.scalars(
        select(ProcurementRecord)
        .where(ProcurementRecord.shipment_date.isnot(None),
               ProcurementRecord.shipment_date <= today)
        .order_by(ProcurementRecord.shipment_date.asc())
        .limit(limit)
    ).all()
    return format_overdue(rows, today)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_gather.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin_digest_service.py backend/tests/test_admin_digest_gather.py
git commit -m "feat(digest): gather counts/critical/risk/overdue for admin digest"
```

---

### Task 4: Heated-conversation detection + AI summary (LLM with fallback)

**Files:**
- Modify: `backend/app/services/admin_digest_service.py`
- Test: `backend/tests/test_admin_digest_ai.py`

**Interfaces:**
- Consumes: `ai_service.is_enabled() -> bool`, `ai_service.complete_json(system, user, temperature=...) -> dict` (`backend/app/services/ai_service.py`); `_gather_*` from Task 3.
- Produces:
  - `_gather_heated(db, limit) -> list[dict]` — items `{"supplier","po","tone","score","msg_count","recent_count","quote"}`.
  - `_ai_summary(counts: dict, critical: list[dict], heated: list[dict]) -> str`.
  - `rank_heated_candidates(rows) -> list` (pure: order PO activity rows by `recent_count*2 + msg_count`, escalation tiebreak).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_digest_ai.py`:

```python
import unittest
from unittest.mock import patch

from app.services import admin_digest_service as svc


class HeatedAndSummaryTests(unittest.TestCase):
    def test_ai_summary_falls_back_when_disabled(self):
        counts = {"active": 100, "critical": 5, "overdue": 9,
                  "signals": {"GREEN": 70, "YELLOW": 16, "RED": 9, "BLACK": 5},
                  "open_followups": 12, "new_replies": 3}
        with patch.object(svc.ai_service, "is_enabled", return_value=False):
            text = svc._ai_summary(counts, critical=[], heated=[])
        self.assertIn("5", text)         # mentions critical count
        self.assertIn("overdue", text.lower())
        self.assertTrue(len(text) > 0)

    def test_ai_summary_uses_llm_when_enabled(self):
        counts = {"active": 1, "critical": 1, "overdue": 1,
                  "signals": {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 1},
                  "open_followups": 0, "new_replies": 0}
        with patch.object(svc.ai_service, "is_enabled", return_value=True), \
             patch.object(svc.ai_service, "complete_json",
                          return_value={"summary": "LLM written paragraph."}) as cj:
            text = svc._ai_summary(counts, critical=[], heated=[])
        self.assertEqual(text, "LLM written paragraph.")
        cj.assert_called_once()

    def test_ai_summary_survives_llm_exception(self):
        counts = {"active": 1, "critical": 0, "overdue": 0,
                  "signals": {"GREEN": 1, "YELLOW": 0, "RED": 0, "BLACK": 0},
                  "open_followups": 0, "new_replies": 0}
        with patch.object(svc.ai_service, "is_enabled", return_value=True), \
             patch.object(svc.ai_service, "complete_json", side_effect=RuntimeError("boom")):
            text = svc._ai_summary(counts, critical=[], heated=[])
        self.assertTrue(len(text) > 0)   # fell back, no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_ai.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'ai_service'` (import not yet added) or `_ai_summary` missing.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/admin_digest_service.py`, add the import near the top:

```python
from . import ai_service
```

Then append:

```python
HEAT_TONE_LABELS = {"frustrated", "tense", "angry", "calm", "neutral"}


def _fallback_summary(counts: dict) -> str:
    s = counts["signals"]
    return (
        f"{counts['critical']} critical POs need attention and "
        f"{counts['overdue']} shipments are overdue. Signal mix is "
        f"{s['GREEN']} green / {s['YELLOW']} yellow / {s['RED']} red / {s['BLACK']} black "
        f"across {counts['active']} active POs, with {counts['open_followups']} open "
        f"follow-ups and {counts['new_replies']} new supplier replies in the last 24 hours."
    )


def _ai_summary(counts: dict, critical: list[dict], heated: list[dict]) -> str:
    if not ai_service.is_enabled():
        return _fallback_summary(counts)
    try:
        crit = "; ".join(f"{c['po']} {c['supplier']} ({c['signal']}, risk {c['risk']})"
                         for c in critical[:5]) or "none"
        heat = "; ".join(f"{h['supplier']} {h['po']} ({h['tone']})" for h in heated[:5]) or "none"
        result = ai_service.complete_json(
            system=("You are Harmony Intelligence, a procurement analyst. Write ONE concise "
                    "paragraph (max 60 words) summarizing the day's supplier delivery state. "
                    "Return JSON {\"summary\": \"...\"}. No markdown, no lists."),
            user=(f"Counts: {counts}. Most critical: {crit}. Heated threads: {heat}."),
            temperature=0.3,
        )
        text = (result or {}).get("summary", "").strip()
        return text or _fallback_summary(counts)
    except Exception:  # noqa: BLE001
        log.exception("admin digest AI summary failed; using fallback")
        return _fallback_summary(counts)


def rank_heated_candidates(rows) -> list:
    """rows: objects with .recent_count, .msg_count, .escalation_level."""
    esc_weight = {"CRITICAL": 3, "LEVEL_2": 2, "LEVEL_1": 1, "NONE": 0}
    return sorted(
        rows,
        key=lambda r: (r.recent_count * 2 + r.msg_count
                       + esc_weight.get(getattr(r, "escalation_level", "NONE"), 0)),
        reverse=True,
    )


def _gather_heated(db: Session, limit: int) -> list[dict]:
    """Rank PO threads by recent activity, then LLM-score tone (fallback: heuristic)."""
    since = datetime.utcnow() - timedelta(hours=24)
    # Aggregate per-PO message activity.
    agg = db.execute(
        select(
            CommunicationMessage.supplier_po_no,
            CommunicationMessage.supplier_name,
            func.count().label("msg_count"),
            func.sum(case((CommunicationMessage.received_at >= since, 1), else_=0)
                     ).label("recent_count"),
        )
        .where(CommunicationMessage.supplier_po_no.isnot(None))
        .group_by(CommunicationMessage.supplier_po_no, CommunicationMessage.supplier_name)
        .order_by(func.count().desc())
        .limit(max(limit * 3, 6))
    ).all()
    candidates = [
        type("C", (), {"supplier_po_no": a[0], "supplier_name": a[1],
                       "msg_count": int(a[2] or 0), "recent_count": int(a[3] or 0),
                       "escalation_level": "NONE"})()
        for a in agg
    ]
    ranked = rank_heated_candidates(candidates)[:limit]
    out: list[dict] = []
    for c in ranked:
        tone, score, quote = _score_tone(db, c)
        if tone in ("frustrated", "tense", "angry"):
            out.append({"supplier": c.supplier_name or "—", "po": c.supplier_po_no or "—",
                        "tone": tone.title(), "score": score,
                        "msg_count": c.msg_count, "recent_count": c.recent_count, "quote": quote})
    return out


def _score_tone(db: Session, candidate) -> tuple[str, float, str | None]:
    """Return (tone, score, quote). LLM if enabled, else heuristic by activity."""
    last = db.scalars(
        select(CommunicationMessage)
        .where(CommunicationMessage.supplier_po_no == candidate.supplier_po_no,
               CommunicationMessage.direction == "INCOMING")
        .order_by(CommunicationMessage.received_at.desc().nullslast())
        .limit(1)
    ).first()
    quote = (last.body or "")[:160].strip() if last and last.body else None
    if not ai_service.is_enabled() or not quote:
        # Heuristic: lots of recent back-and-forth reads as tense.
        tone = "tense" if candidate.recent_count >= 3 else "neutral"
        return tone, min(0.6, 0.2 + candidate.recent_count * 0.1), quote
    try:
        result = ai_service.complete_json(
            system=("Classify the tone of this supplier message. Return JSON "
                    "{\"tone\": one of [calm, neutral, tense, frustrated, angry], "
                    "\"score\": 0..1}."),
            user=quote,
            temperature=0.0,
        )
        tone = str((result or {}).get("tone", "neutral")).lower()
        if tone not in HEAT_TONE_LABELS:
            tone = "neutral"
        score = float((result or {}).get("score", 0.5) or 0.5)
        return tone, round(score, 2), quote
    except Exception:  # noqa: BLE001
        log.exception("admin digest tone scoring failed; using heuristic")
        tone = "tense" if candidate.recent_count >= 3 else "neutral"
        return tone, min(0.6, 0.2 + candidate.recent_count * 0.1), quote
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_ai.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin_digest_service.py backend/tests/test_admin_digest_ai.py
git commit -m "feat(digest): heated-thread tone scoring + AI summary with fallbacks"
```

---

### Task 5: HTML rendering

**Files:**
- Modify: `backend/app/services/admin_digest_service.py`
- Test: `backend/tests/test_admin_digest_render.py`

**Interfaces:**
- Consumes: `brand_email.header_html`, `brand_email.shell`, `brand_email.footer_html`, brand color constants (`backend/app/services/brand_email.py`); the data shapes from Tasks 3–4.
- Produces:
  - `build_digest_data(db, cfg) -> dict` — assembles `{generated_at_local, counts, summary, critical, heated, risk, overdue}` honoring `cfg["sections"]` and `cfg["limits"]` (a disabled section is an empty list / omitted key).
  - `render_digest_html(data, cfg) -> str` — full email HTML string. Mirrors `backend/app/services/templates/digest_sample.html`. Only renders sections whose `cfg["sections"][name]` is true and that have data.
  - `digest_subject(data) -> str` → `"Harmony Intelligence Summary — 27 June 2026"`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_digest_render.py`:

```python
import unittest

from app.services import admin_digest_service as svc

CFG = {
    "sections": {"counts": True, "summary": True, "critical": True,
                 "heated": False, "risk": True, "overdue": True},
    "limits": {"critical": 10, "heated": 5, "risk": 10, "overdue": 15},
    "timezone": "Asia/Kolkata", "send_hour": 9,
}

DATA = {
    "generated_at_local": "27 June 2026 · 09:00 IST",
    "counts": {"active": 418, "open_followups": 63, "overdue": 17, "critical": 12,
               "new_replies": 9, "signals": {"GREEN": 291, "YELLOW": 84, "RED": 31, "BLACK": 12}},
    "summary": "Twelve critical POs need attention.",
    "critical": [{"po": "HO-PO-1", "supplier": "Shree Steel", "material": "Flange",
                  "signal": "Black", "days_late": 19, "risk": 96}],
    "heated": [{"supplier": "Shree Steel", "po": "HO-PO-1", "tone": "Frustrated",
                "score": 0.88, "msg_count": 14, "recent_count": 5, "quote": "stop emailing"}],
    "risk": [{"po": "HO-PO-2", "supplier": "Metro", "reason": "no date", "score": 84}],
    "overdue": [{"po": "HO-PO-1", "supplier": "Shree", "shipment": "08 Jun",
                 "status": "Overdue", "days_late": 19}],
}


class RenderTests(unittest.TestCase):
    def test_title_and_brand_present(self):
        html = svc.render_digest_html(DATA, CFG)
        self.assertIn("Harmony Intelligence Summary", html)
        self.assertIn("#E11D2E", html)
        self.assertIn("418", html)            # a count rendered

    def test_disabled_section_omitted(self):
        html = svc.render_digest_html(DATA, CFG)
        self.assertNotIn("Heated conversations", html)   # heated disabled in CFG
        self.assertIn("Most critical", html)             # critical enabled

    def test_subject_uses_date(self):
        self.assertEqual(svc.digest_subject(DATA),
                         "Harmony Intelligence Summary — 27 June 2026")

    def test_no_emoji_or_arrows(self):
        html = svc.render_digest_html(DATA, CFG)
        for ch in ("✨", "→", "↗", "🔥"):
            self.assertNotIn(ch, html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_render.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'render_digest_html'`.

- [ ] **Step 3: Write minimal implementation**

In `admin_digest_service.py` add `from . import brand_email` to the imports, then append. The markup mirrors `digest_sample.html` (open it for the exact inline styles); the helpers below produce the same structure:

```python
INK = brand_email.BRAND_INK      # "#1f2937"
MUTED = brand_email.BRAND_MUTED  # "#6B7280"
RED = brand_email.BRAND_RED      # "#E11D2E"
HAIR = brand_email.BRAND_BORDER  # "#ECECEC"

_LABEL = (f'font-size:11px;font-weight:700;letter-spacing:1.5px;'
          f'text-transform:uppercase;color:{MUTED};padding-bottom:12px;')
_SECTION = f'padding:24px 32px 0;'
_DIVIDER = f'border-top:1px solid {HAIR};padding-top:20px;'


def digest_subject(data: dict) -> str:
    date_part = data["generated_at_local"].split(" · ")[0]
    return f"Harmony Intelligence Summary — {date_part}"


def _esc(v: Any) -> str:
    s = "" if v is None else str(v)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _section(label: str, inner: str, *, first: bool = False) -> str:
    div = "" if first else _DIVIDER
    return (f'<div style="{_SECTION}"><div style="{div}">'
            f'<div style="{_LABEL}">{label}</div>{inner}</div></div>')


def _counts_html(c: dict) -> str:
    tiles = [("Active POs", c["active"], INK), ("Open follow-ups", c["open_followups"], INK),
             ("Overdue", c["overdue"], RED), ("Critical", c["critical"], INK),
             ("New replies", c["new_replies"], INK)]
    cells = "".join(
        f'<td style="padding:0 16px;border-right:1px solid {HAIR};">'
        f'<div style="font-size:28px;font-weight:700;color:{color};">{val}</div>'
        f'<div style="font-size:12px;color:{MUTED};padding-top:3px;">{_esc(lbl)}</div></td>'
        for lbl, val, color in tiles)
    s = c["signals"]
    sig = (f'<div style="font-size:13px;color:{MUTED};padding-top:16px;">'
           f'<span style="color:{INK};">Signal mix</span>&nbsp;&nbsp;'
           f'Green <b style="color:{INK};">{s["GREEN"]}</b> &middot; '
           f'Yellow <b style="color:{INK};">{s["YELLOW"]}</b> &middot; '
           f'Red <b style="color:{INK};">{s["RED"]}</b> &middot; '
           f'Black <b style="color:{INK};">{s["BLACK"]}</b></div>')
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            f'<tr>{cells}</tr></table>{sig}')


def _table(headers: list[tuple[str, str]], rows: list[str]) -> str:
    head = "".join(
        f'<td style="font-size:11px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;'
        f'color:#9aa0a6;padding:0 0 8px;{align}">{_esc(h)}</td>' for h, align in headers)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse;"><tr style="border-bottom:1px solid {HAIR};">'
            f'{head}</tr>{"".join(rows)}</table>')


def _critical_html(items: list[dict]) -> str:
    rows = []
    for it in items:
        late = "—" if it["days_late"] is None else it["days_late"]
        rows.append(
            f'<tr style="border-bottom:1px solid #F4F4F5;">'
            f'<td style="padding:13px 0;font-size:13px;color:{INK};"><b>{_esc(it["po"])}</b><br>'
            f'<span style="font-size:12px;color:{MUTED};">{_esc(it["supplier"])} &middot; {_esc(it["material"])}</span></td>'
            f'<td style="padding:13px 0;font-size:12px;font-weight:700;color:{INK};">{_esc(it["signal"])}</td>'
            f'<td style="padding:13px 0;font-size:13px;font-weight:700;color:{RED};text-align:right;">{late}</td>'
            f'<td style="padding:13px 0;font-size:13px;font-weight:700;color:{INK};text-align:right;">{_esc(it["risk"])}</td></tr>')
    return _table([("PO / Supplier", ""), ("Signal", ""),
                   ("Days late", "text-align:right;"), ("Risk", "text-align:right;")], rows)


def _heated_html(items: list[dict]) -> str:
    blocks = []
    for it in items:
        blocks.append(
            f'<div style="padding-bottom:14px;">'
            f'<table role="presentation" width="100%"><tr>'
            f'<td style="font-size:13px;font-weight:700;color:{INK};">{_esc(it["supplier"])} &middot; {_esc(it["po"])}</td>'
            f'<td style="text-align:right;font-size:12px;color:{RED};font-weight:700;">{_esc(it["tone"])} &middot; {it["score"]}</td>'
            f'</tr></table>'
            f'<div style="font-size:12px;color:{MUTED};padding-top:5px;line-height:1.55;">'
            f'{it["msg_count"]} messages, {it["recent_count"]} in the last 24h.'
            + (f' &ldquo;<i>{_esc(it["quote"])}</i>&rdquo;' if it.get("quote") else "")
            + '</div></div>')
    return "".join(blocks)


def _risk_html(items: list[dict]) -> str:
    rows = [
        f'<tr style="border-bottom:1px solid #F4F4F5;">'
        f'<td style="padding:12px 0;font-size:13px;color:{INK};"><b>{_esc(it["po"])}</b> &middot; '
        f'<span style="color:{MUTED};">{_esc(it["supplier"])}</span></td>'
        f'<td style="padding:12px 0;font-size:12px;color:{MUTED};">{_esc(it["reason"])}</td>'
        f'<td style="padding:12px 0;font-size:13px;font-weight:700;color:{INK};text-align:right;">{_esc(it["score"])}</td></tr>'
        for it in items]
    return _table([("PO / Supplier", ""), ("Why", ""), ("Score", "text-align:right;")], rows)


def _overdue_html(items: list[dict]) -> str:
    rows = [
        f'<tr style="border-bottom:1px solid #F4F4F5;">'
        f'<td style="padding:12px 0;font-size:13px;color:{INK};"><b>{_esc(it["po"])}</b> &middot; '
        f'<span style="color:{MUTED};">{_esc(it["supplier"])}</span></td>'
        f'<td style="padding:12px 0;font-size:12px;font-weight:700;color:{RED};">{_esc(it["shipment"])}</td>'
        f'<td style="padding:12px 0;font-size:12px;color:{MUTED};text-align:right;">{_esc(it["status"])}</td></tr>'
        for it in items]
    return _table([("PO / Supplier", ""), ("Shipment", ""), ("Status", "text-align:right;")], rows)


def render_digest_html(data: dict, cfg: dict) -> str:
    sec = cfg.get("sections", {})
    parts = [
        f'<div style="padding:28px 32px 0;">'
        f'<div style="font-size:22px;font-weight:700;letter-spacing:-.2px;color:{INK};">Harmony Intelligence Summary</div>'
        f'<div style="font-size:13px;color:{MUTED};padding-top:5px;">{_esc(data["generated_at_local"])} &middot; covering the last 24 hours</div></div>'
    ]
    if sec.get("counts", True):
        parts.append(_section("At a glance", _counts_html(data["counts"]), first=True))
    if sec.get("summary", True) and data.get("summary"):
        parts.append(_section("Summary",
                     f'<div style="font-size:14px;line-height:1.6;color:{INK};">{_esc(data["summary"])}</div>'))
    if sec.get("critical", True) and data.get("critical"):
        parts.append(_section("Most critical", _critical_html(data["critical"])))
    if sec.get("heated", True) and data.get("heated"):
        parts.append(_section("Heated conversations", _heated_html(data["heated"])))
    if sec.get("risk", True) and data.get("risk"):
        parts.append(_section("Top delay-risk POs", _risk_html(data["risk"])))
    if sec.get("overdue", True) and data.get("overdue"):
        parts.append(_section("Overdue & due today", _overdue_html(data["overdue"])))
    parts.append('<div style="padding:28px 32px;"></div>')
    inner = (brand_email.header_html("Intelligence Summary") + "".join(parts)
             + brand_email.footer_html(
                 "You receive this because you are on the Harmony Intelligence Summary list. "
                 "Manage recipients, send time, and sections in Settings &rarr; Daily Summary."))
    return brand_email.shell(inner)


def build_digest_data(db: Session, cfg: dict) -> dict:
    from zoneinfo import ZoneInfo
    sec = cfg.get("sections", {})
    lim = cfg.get("limits", {})
    now_local = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(
        ZoneInfo(cfg.get("timezone", "Asia/Kolkata")))
    tz_abbr = "IST" if cfg.get("timezone") == "Asia/Kolkata" else now_local.tzname() or ""
    counts = _gather_counts(db) if sec.get("counts", True) else None
    critical = _gather_critical(db, lim.get("critical", 10)) if sec.get("critical", True) else []
    heated = _gather_heated(db, lim.get("heated", 5)) if sec.get("heated", True) else []
    risk = _gather_risk(db, lim.get("risk", 10)) if sec.get("risk", True) else []
    overdue = _gather_overdue(db, lim.get("overdue", 15)) if sec.get("overdue", True) else []
    summary = (_ai_summary(counts, critical, heated)
               if sec.get("summary", True) and counts else "")
    return {
        "generated_at_local": now_local.strftime(f"%d %B %Y · %H:%M {tz_abbr}").lstrip("0"),
        "counts": counts or {"active": 0, "open_followups": 0, "overdue": 0, "critical": 0,
                             "new_replies": 0, "signals": {"GREEN": 0, "YELLOW": 0, "RED": 0, "BLACK": 0}},
        "summary": summary, "critical": critical, "heated": heated, "risk": risk, "overdue": overdue,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_render.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin_digest_service.py backend/tests/test_admin_digest_render.py
git commit -m "feat(digest): branded HTML rendering mirroring digest_sample.html"
```

---

### Task 6: Send orchestration + once-per-day due gating

**Files:**
- Modify: `backend/app/services/admin_digest_service.py`
- Test: `backend/tests/test_admin_digest_send.py`

**Interfaces:**
- Consumes: `settings_service.get_admin_digest/set/mark_admin_digest_sent` (Task 1); `mail_send_worker.send_html_email` (Task 2); `build_digest_data`/`render_digest_html`/`digest_subject` (Task 5); `settings.SMTP_ENABLED` via `core.config`.
- Produces:
  - `send_digest_if_due(db, *, now: datetime | None = None) -> dict` — the runner entry point. Returns a status dict (`{"sent": int}` or `{"skipped": reason}`).
  - `send_test_digest(db, to_email: str) -> dict` — builds + sends immediately to one address, ignoring schedule/enabled, never stamps `last_sent_date`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_digest_send.py`:

```python
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services import admin_digest_service as svc

# 2026-06-27 04:00 UTC == 09:30 IST (after send_hour=9)
AFTER = datetime(2026, 6, 27, 4, 0)
# 2026-06-27 02:00 UTC == 07:30 IST (before send_hour=9)
BEFORE = datetime(2026, 6, 27, 2, 0)

BASE_CFG = {
    "enabled": True, "recipients": ["a@x.com"], "send_hour": 9, "timezone": "Asia/Kolkata",
    "sections": {"counts": True, "summary": False, "critical": False, "heated": False,
                 "risk": False, "overdue": False},
    "limits": {"critical": 10, "heated": 5, "risk": 10, "overdue": 15}, "last_sent_date": None,
}


def _cfg(**over):
    c = {**BASE_CFG, **over}
    return c


class SendIfDueTests(unittest.TestCase):
    def _patches(self, cfg):
        return (
            patch.object(svc.settings_service, "get_admin_digest", return_value=cfg),
            patch.object(svc.settings_service, "mark_admin_digest_sent"),
            patch.object(svc, "build_digest_data", return_value={"generated_at_local": "27 June 2026 · 09:30 IST"}),
            patch.object(svc, "render_digest_html", return_value="<html></html>"),
            patch.object(svc, "digest_subject", return_value="Harmony Intelligence Summary — 27 June 2026"),
            patch.object(svc.settings, "SMTP_ENABLED", True),
        )

    def test_skips_when_disabled(self):
        with patch.object(svc.settings_service, "get_admin_digest", return_value=_cfg(enabled=False)):
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertIn("skipped", out)

    def test_skips_when_no_recipients(self):
        with patch.object(svc.settings_service, "get_admin_digest", return_value=_cfg(recipients=[])):
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertEqual(out["skipped"], "no recipients")

    def test_skips_before_send_hour(self):
        with patch.object(svc.settings_service, "get_admin_digest", return_value=_cfg()):
            out = svc.send_digest_if_due(MagicMock(), now=BEFORE)
        self.assertEqual(out["skipped"], "before send_hour")

    def test_skips_when_already_sent_today(self):
        with patch.object(svc.settings_service, "get_admin_digest",
                          return_value=_cfg(last_sent_date="2026-06-27")):
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertEqual(out["skipped"], "already sent today")

    def test_sends_and_marks_when_due(self):
        cfg = _cfg()
        p = self._patches(cfg)
        with p[0], p[1] as mark, p[2], p[3], p[4], p[5], \
             patch.object(svc.mail_send_worker, "send_html_email",
                          return_value={"sent": True, "recipients": 1, "reason": ""}) as send:
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertEqual(out["sent"], 1)
        send.assert_called_once()
        mark.assert_called_once_with(unittest.mock.ANY, "2026-06-27")

    def test_does_not_mark_when_send_fails(self):
        cfg = _cfg()
        p = self._patches(cfg)
        with p[0], p[1] as mark, p[2], p[3], p[4], p[5], \
             patch.object(svc.mail_send_worker, "send_html_email",
                          return_value={"sent": False, "recipients": 0, "reason": "smtp down"}):
            out = svc.send_digest_if_due(MagicMock(), now=AFTER)
        self.assertIn("error", out)
        mark.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_send.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'send_digest_if_due'`.

- [ ] **Step 3: Write minimal implementation**

In `admin_digest_service.py` add imports near the top:

```python
from zoneinfo import ZoneInfo

from . import settings_service
from ..core.config import settings
from ..workers import mail_send_worker
```

Append:

```python
def send_digest_if_due(db: Session, *, now: datetime | None = None) -> dict:
    cfg = settings_service.get_admin_digest(db)
    if not cfg["enabled"]:
        return {"skipped": "disabled"}
    if not cfg["recipients"]:
        return {"skipped": "no recipients"}
    if not getattr(settings, "SMTP_ENABLED", False):
        return {"skipped": "smtp disabled"}
    now_utc = now or datetime.utcnow()
    local = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(cfg["timezone"]))
    if local.hour < int(cfg["send_hour"]):
        return {"skipped": "before send_hour"}
    today_iso = local.date().isoformat()
    if cfg.get("last_sent_date") == today_iso:
        return {"skipped": "already sent today"}

    data = build_digest_data(db, cfg)
    html = render_digest_html(data, cfg)
    result = mail_send_worker.send_html_email(cfg["recipients"], digest_subject(data), html)
    if not result.get("sent"):
        return {"error": True, "reason": result.get("reason", "send failed")}
    settings_service.mark_admin_digest_sent(db, today_iso)
    return {"sent": result.get("recipients", len(cfg["recipients"])), "date": today_iso}


def send_test_digest(db: Session, to_email: str) -> dict:
    cfg = settings_service.get_admin_digest(db)
    data = build_digest_data(db, cfg)
    html = render_digest_html(data, cfg)
    return mail_send_worker.send_html_email([to_email], digest_subject(data), html)
```

Note: `build_digest_data` already imports `ZoneInfo` locally — remove that local import now that it's module-level (keep one definition; the module-level import wins).

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_send.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin_digest_service.py backend/tests/test_admin_digest_send.py
git commit -m "feat(digest): once-per-day due gating + test send"
```

---

### Task 7: Register the scheduler job

**Files:**
- Modify: `backend/app/scheduler/jobs.py`
- Test: `backend/tests/test_admin_digest_job.py`

**Interfaces:**
- Consumes: `EngineJobSpec` (`engine_registry.py`), `SessionLocal`, `admin_digest_service.send_digest_if_due`.
- Produces: `admin_digest_runner() -> dict[str, Any]`; a new `EngineJobSpec(job_name="admin_digest_cron", ...)` appended to `JOB_SPECS`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_digest_job.py`:

```python
import unittest
from unittest.mock import patch

from app.scheduler import jobs


class AdminDigestJobTests(unittest.TestCase):
    def test_spec_registered(self):
        names = [s.job_name for s in jobs.JOB_SPECS]
        self.assertIn("admin_digest_cron", names)
        spec = next(s for s in jobs.JOB_SPECS if s.job_name == "admin_digest_cron")
        self.assertEqual(spec.default_interval_minutes, 15)
        self.assertEqual(spec.runner, jobs.admin_digest_runner)

    def test_runner_delegates_to_service(self):
        with patch("app.scheduler.jobs.SessionLocal") as SL, \
             patch("app.services.admin_digest_service.send_digest_if_due",
                   return_value={"sent": 2}) as send:
            out = jobs.admin_digest_runner()
        self.assertEqual(out, {"sent": 2})
        send.assert_called_once()
        SL.return_value.close.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_job.py -v`
Expected: FAIL — `AttributeError: module 'app.scheduler.jobs' has no attribute 'admin_digest_runner'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/scheduler/jobs.py`, add the runner after `crm_ingestion_runner` (around line 202):

```python
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
```

Then append a spec to the `JOB_SPECS` list (after the `crm_ingestion_cron` entry, before the closing `]`):

```python
    EngineJobSpec(
        job_name="admin_digest_cron",
        display_name="Harmony Intelligence Summary",
        description="Email the daily admin digest to configured recipients at the set hour.",
        default_interval_minutes=15,
        runner=admin_digest_runner,
        category="OTHER",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_job.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/scheduler/jobs.py backend/tests/test_admin_digest_job.py
git commit -m "feat(digest): register admin_digest_cron scheduler job (15-min ticker)"
```

---

### Task 8: Backend API routes

**Files:**
- Modify: `backend/app/routers/settings.py`
- Test: `backend/tests/test_admin_digest_routes.py`

**Interfaces:**
- Consumes: existing `router` (`APIRouter(prefix="/api/settings")`), `_MGR = [Depends(require_manager)]`, `get_db`; `settings_service.get_admin_digest/set_admin_digest`; `admin_digest_service.send_test_digest`; `get_current_user` for the test endpoint's caller email.
- Produces three endpoints:
  - `GET /api/settings/admin-digest` → `{"admin_digest": cfg}`
  - `PUT /api/settings/admin-digest` (manager) body = partial config → `{"admin_digest": cfg}`
  - `POST /api/settings/admin-digest/test` (manager) → sends to the caller's email, returns the send result dict.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_digest_routes.py`:

```python
import unittest
from unittest.mock import MagicMock, patch

from app.routers import settings as settings_router


class AdminDigestRouteTests(unittest.TestCase):
    def test_get_returns_config(self):
        db = MagicMock()
        with patch.object(settings_router.settings_service, "get_admin_digest",
                          return_value={"enabled": False, "recipients": []}):
            out = settings_router.get_admin_digest_settings(db=db)
        self.assertIn("admin_digest", out)
        self.assertFalse(out["admin_digest"]["enabled"])

    def test_put_persists_partial_update(self):
        db = MagicMock()
        payload = settings_router.AdminDigestUpdate(enabled=True, recipients=["a@x.com"])
        with patch.object(settings_router.settings_service, "set_admin_digest",
                          return_value={"enabled": True, "recipients": ["a@x.com"]}) as setter:
            out = settings_router.update_admin_digest_settings(payload, db=db)
        setter.assert_called_once()
        self.assertTrue(out["admin_digest"]["enabled"])

    def test_test_endpoint_sends_to_caller(self):
        db = MagicMock()
        user = MagicMock(email="me@hariom.com")
        with patch.object(settings_router.admin_digest_service, "send_test_digest",
                          return_value={"sent": True, "recipients": 1}) as send:
            out = settings_router.send_admin_digest_test(db=db, current_user=user)
        send.assert_called_once_with(db, "me@hariom.com")
        self.assertTrue(out["sent"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_routes.py -v`
Expected: FAIL — `AttributeError: module 'app.routers.settings' has no attribute 'get_admin_digest_settings'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/routers/settings.py`: add imports near the other imports — `from pydantic import BaseModel`, `from ..core.deps import get_current_user`, `from ..services import settings_service, admin_digest_service` (extend existing import lines as needed; `settings_service` is likely already imported — reuse it). Add the schema and endpoints (place after the `/followup` route):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_digest_routes.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full backend suite (regression check) + Commit**

Run: `backend/.venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass.

```bash
git add backend/app/routers/settings.py backend/tests/test_admin_digest_routes.py
git commit -m "feat(digest): /api/settings/admin-digest GET/PUT/test endpoints"
```

---

### Task 9: Frontend — API client + "Daily Summary" settings card

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/settings/page.tsx`

**Interfaces:**
- Consumes: existing `api` object + `http<T>` helper in `api.ts` (pattern at `getSchedulerSettings`/`updateSchedulerIntervals`); existing card/section layout in `settings/page.tsx`.
- Produces:
  - Type `AdminDigestConfig` in `types.ts`.
  - `api.getAdminDigest()`, `api.updateAdminDigest(values)`, `api.sendAdminDigestTest()`.
  - A "Daily Summary" card rendered on the Settings page with enabled toggle, recipients, send hour, timezone, section checkboxes, limits, Save, and "Send test to me".

- [ ] **Step 1: Add the type**

In `frontend/lib/types.ts` add:

```ts
export interface AdminDigestConfig {
  enabled: boolean;
  recipients: string[];
  send_hour: number;
  timezone: string;
  sections: Record<string, boolean>;
  limits: Record<string, number>;
  last_sent_date: string | null;
}
```

- [ ] **Step 2: Add API client methods**

In `frontend/lib/api.ts`, inside the `api` object (next to `getSchedulerSettings`), add:

```ts
  getAdminDigest: () =>
    http<{ admin_digest: AdminDigestConfig }>("/api/settings/admin-digest"),

  updateAdminDigest: (values: Partial<AdminDigestConfig>) =>
    http<{ admin_digest: AdminDigestConfig }>("/api/settings/admin-digest", {
      method: "PUT",
      body: JSON.stringify(values),
    }),

  sendAdminDigestTest: () =>
    http<{ sent: boolean; recipients: number; reason?: string }>(
      "/api/settings/admin-digest/test",
      { method: "POST" }
    ),
```

Add `AdminDigestConfig` to the type import at the top of `api.ts` (the line importing from `./types`).

- [ ] **Step 3: Add the settings card**

In `frontend/app/settings/page.tsx`:

1. Add state near the other `useState` hooks (around line 70):

```tsx
  const [digest, setDigest] = useState<AdminDigestConfig | null>(null);
  const [digestRecipients, setDigestRecipients] = useState("");
```

2. In the existing load effect (where `api.getSchedulerSettings()` is awaited, ~line 83), add `api.getAdminDigest()` to the `Promise.all` and after resolving:

```tsx
      setDigest(digestResp.admin_digest);
      setDigestRecipients((digestResp.admin_digest.recipients || []).join(", "));
```

3. Add handlers near `handleSaveScheduler` (~line 137):

```tsx
  async function handleSaveDigest() {
    if (!digest) return;
    try {
      const recipients = digestRecipients
        .split(",").map((s) => s.trim()).filter(Boolean);
      const res = await api.updateAdminDigest({ ...digest, recipients });
      setDigest(res.admin_digest);
      setDigestRecipients((res.admin_digest.recipients || []).join(", "));
      setMessage("Daily Summary settings saved.");
    } catch (e) {
      setMessage("Failed to save Daily Summary settings.");
    }
  }

  async function handleTestDigest() {
    try {
      const res = await api.sendAdminDigestTest();
      setMessage(res.sent ? "Test summary sent to your email." : `Not sent: ${res.reason}`);
    } catch (e) {
      setMessage("Failed to send test summary.");
    }
  }
```

4. Render the card in the page body (place it near the Scheduler Intervals card). Match the existing card wrapper classes used on the page (e.g. the `title="Mail Engine Control"` card pattern):

```tsx
  {digest && (
    <section className="rounded-lg border border-brand-border bg-white p-4">
      <h2 className="text-lg font-semibold text-brand-ink">Daily Summary</h2>
      <p className="text-xs text-brand-muted mb-3">
        Harmony Intelligence Summary — emailed to the recipients below each day at the set hour.
      </p>

      <label className="flex items-center gap-2 text-sm mb-3">
        <input type="checkbox" checked={digest.enabled}
          onChange={(e) => setDigest({ ...digest, enabled: e.target.checked })} />
        Enabled
      </label>

      <label className="block text-sm mb-3">
        Recipients (comma-separated)
        <input className="mt-1 w-full rounded border px-2 py-1 text-sm"
          value={digestRecipients}
          onChange={(e) => setDigestRecipients(e.target.value)}
          placeholder="ops@hariom.com, lead@hariom.com" />
      </label>

      <div className="flex gap-4 mb-3">
        <label className="text-sm">
          Send hour (0–23)
          <input type="number" min={0} max={23}
            className="mt-1 w-20 rounded border px-2 py-1 text-sm"
            value={digest.send_hour}
            onChange={(e) => setDigest({ ...digest, send_hour: Number(e.target.value) })} />
        </label>
        <label className="text-sm">
          Timezone
          <input className="mt-1 w-44 rounded border px-2 py-1 text-sm"
            value={digest.timezone}
            onChange={(e) => setDigest({ ...digest, timezone: e.target.value })} />
        </label>
      </div>

      <div className="mb-3">
        <div className="text-sm font-medium mb-1">Sections</div>
        <div className="flex flex-wrap gap-3">
          {["counts", "summary", "critical", "heated", "risk", "overdue"].map((key) => (
            <label key={key} className="flex items-center gap-1 text-sm capitalize">
              <input type="checkbox" checked={!!digest.sections[key]}
                onChange={(e) =>
                  setDigest({ ...digest, sections: { ...digest.sections, [key]: e.target.checked } })} />
              {key}
            </label>
          ))}
        </div>
      </div>

      <div className="mb-3">
        <div className="text-sm font-medium mb-1">Row limits</div>
        <div className="flex flex-wrap gap-3">
          {["critical", "heated", "risk", "overdue"].map((key) => (
            <label key={key} className="text-sm capitalize">
              {key}
              <input type="number" min={1} max={100}
                className="mt-1 ml-1 w-16 rounded border px-2 py-1 text-sm"
                value={digest.limits[key] ?? 10}
                onChange={(e) =>
                  setDigest({ ...digest, limits: { ...digest.limits, [key]: Number(e.target.value) } })} />
            </label>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        <button onClick={handleSaveDigest}
          className="rounded bg-brand-red px-3 py-1.5 text-sm font-medium text-white">
          Save
        </button>
        <button onClick={handleTestDigest}
          className="rounded border border-brand-border px-3 py-1.5 text-sm font-medium">
          Send test to me
        </button>
      </div>
      {digest.last_sent_date && (
        <p className="text-xs text-brand-muted mt-2">Last sent: {digest.last_sent_date}</p>
      )}
    </section>
  )}
```

5. Add `AdminDigestConfig` to the `types.ts` import at the top of `page.tsx`, and destructure `digestResp` from the `Promise.all` results array in the load effect (add it as the new last element so existing indices are unchanged).

- [ ] **Step 4: Verify the frontend builds/typechecks**

Run (from `frontend/`): `npm run build` (or `npm run lint && npx tsc --noEmit` if a faster check is configured).
Expected: compiles with no type errors; the new card references resolve.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/lib/types.ts frontend/app/settings/page.tsx
git commit -m "feat(digest): Daily Summary settings card + API client methods"
```

---

## Self-Review

**Spec coverage** (each §):
- §3 email content/layout → Task 5 (render) + sample reference. ✓
- §4 config schema → Task 1. ✓
- §5 scheduling mechanics (ticker + due gate) → Task 6 (gating) + Task 7 (registration). ✓
- §6 components: scheduler job → T7; service → T3/T4/T5/T6; settings_service → T1; routes → T8; frontend card → T9. ✓
- §7 heated detection + LLM fallback → Task 4. ✓
- §8 data sources → Task 3 (counts/critical/risk/overdue) + Task 4 (heated). ✓
- §9 error handling: per-section omission via empty lists (T5 `build_digest_data` + render guards); SMTP-disabled skip + no-stamp-on-failure (T6); EngineJobLog ERROR via runner try/except (T7). ✓
- §10 testing: unit per gather (T3), due logic (T6), LLM fallback (T4), render (T5), routes (T8). ✓
- §2 test endpoint → T8 `POST /admin-digest/test`. ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. The one cross-reference ("mirror digest_sample.html") points to a committed file for exact inline-style values, and the helper functions in Task 5 already produce that structure — not a placeholder.

**Type consistency:** `get_admin_digest`/`set_admin_digest`/`mark_admin_digest_sent` (T1) names match their callers in T6/T8. `send_html_email` signature (T2) matches calls in T6. Data dict keys (`po/supplier/material/signal/days_late/risk`, `tone/score/msg_count/recent_count/quote`, `reason/score`, `shipment/status`) are identical between Task 3/4 producers, Task 5 renderers, and Task 5/6 tests. `admin_digest_runner`/`send_digest_if_due`/`send_test_digest` names match across T6/T7/T8. Frontend `AdminDigestConfig` shape matches the backend `get_admin_digest` return.

**Note on `build_digest_data` ZoneInfo:** Task 5 introduces a local `from zoneinfo import ZoneInfo`; Task 6 promotes it to a module-level import. Final state: one module-level import, local import removed (called out in Task 6 Step 3).
