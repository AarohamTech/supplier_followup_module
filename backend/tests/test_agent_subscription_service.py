"""Tests for the HI-agent subscription service."""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AgentSubscription  # noqa: F401
from app.services import agent_subscription_service as subs


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


class SubscriptionServiceTests(unittest.TestCase):
    def test_create_pending_then_confirm_followup(self) -> None:
        with _temp_db() as db:
            sub = subs.create_pending(
                db, kind="FOLLOWUP", supplier_id=1, procurement_record_id=10,
                supplier_po_no="PO-1", recipient_user_id=5,
                recipient_email="a@x.com", recipient_label="Anjali",
                created_by_user_id=2,
            )
            self.assertEqual(sub.status, "PENDING")
            confirmed = subs.confirm(db, sub.id, now=datetime(2026, 6, 28, 12, 0))
            self.assertEqual(confirmed.status, "ACTIVE")
            self.assertIsNone(confirmed.next_run_at)  # followups have no schedule

    def test_confirm_summary_sets_next_run(self) -> None:
        with _temp_db() as db:
            sub = subs.create_pending(
                db, kind="SCHEDULED_SUMMARY", supplier_id=1, procurement_record_id=10,
                supplier_po_no="PO-1", recipient_user_id=5,
                recipient_email="a@x.com", recipient_label="Anjali",
                created_by_user_id=2, schedule="daily",
            )
            confirmed = subs.confirm(db, sub.id, now=datetime(2026, 6, 28, 12, 0))
            self.assertEqual(confirmed.status, "ACTIVE")
            # 12:00 is past 09:00 → next run is tomorrow 09:00
            self.assertEqual(confirmed.next_run_at, datetime(2026, 6, 29, 9, 0))

    def test_due_summaries_filters_by_next_run(self) -> None:
        with _temp_db() as db:
            sub = subs.create_pending(
                db, kind="SCHEDULED_SUMMARY", supplier_id=1, procurement_record_id=10,
                supplier_po_no="PO-1", recipient_user_id=5,
                recipient_email="a@x.com", recipient_label="A",
                created_by_user_id=2, schedule="daily",
            )
            subs.confirm(db, sub.id, now=datetime(2026, 6, 28, 8, 0))  # next=today 09:00
            self.assertEqual(subs.due_summaries(db, datetime(2026, 6, 28, 8, 30)), [])
            due = subs.due_summaries(db, datetime(2026, 6, 28, 9, 1))
            self.assertEqual([s.id for s in due], [sub.id])

    def test_advance_followup_updates_high_water_mark(self) -> None:
        with _temp_db() as db:
            sub = subs.create_pending(
                db, kind="FOLLOWUP", supplier_id=1, procurement_record_id=10,
                supplier_po_no="PO-1", recipient_user_id=5,
                recipient_email="a@x.com", recipient_label="A", created_by_user_id=2,
            )
            subs.confirm(db, sub.id, now=datetime(2026, 6, 28, 9, 0))
            subs.advance_followup(db, sub, 42)
            db.refresh(sub)
            self.assertEqual(sub.last_forwarded_message_id, 42)
