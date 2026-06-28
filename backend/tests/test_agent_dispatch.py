"""Tests for the HI-agent dispatch cron helpers."""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AgentSubscription, CommunicationMessage, User  # noqa: F401
from app.models.communication_message import CommunicationMessage as CM
from app.scheduler import jobs
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


class DispatchTests(unittest.TestCase):
    def test_followup_forwards_only_new_messages_and_advances_mark(self) -> None:
        with _temp_db() as db:
            old = CM(direction="INCOMING", status="RECEIVED", channel="EMAIL",
                     procurement_record_id=10, supplier_po_no="PO-1",
                     subject="old", body="old body")
            db.add(old); db.commit(); db.refresh(old)
            sub = subs.create_pending(
                db, kind="FOLLOWUP", supplier_id=1, procurement_record_id=10,
                supplier_po_no="PO-1", recipient_user_id=5, recipient_email="a@x.com",
                recipient_label="A", created_by_user_id=2,
            )
            subs.confirm(db, sub.id, now=datetime(2026, 6, 28, 9, 0))
            subs.advance_followup(db, sub, old.id)
            new = CM(direction="INCOMING", status="RECEIVED", channel="EMAIL",
                     procurement_record_id=10, supplier_po_no="PO-1",
                     subject="new", body="new body")
            db.add(new); db.commit(); db.refresh(new)

            sent = []

            def fake_qom(_db, **kw):
                m = CM(direction="OUTGOING", status="READY", channel="EMAIL",
                       to_emails=kw.get("to_emails"), subject=kw.get("subject"),
                       body=kw.get("body"))
                _db.add(m); _db.commit(); _db.refresh(m); sent.append(m.id); return m

            with patch("app.scheduler.jobs.msg_service.queue_outgoing_message", side_effect=fake_qom), \
                 patch("app.scheduler.jobs.mail_send_worker.send_message_now", return_value={"sent": True}), \
                 patch("app.scheduler.jobs.notif.safe", return_value=0):
                count = jobs._dispatch_followups(db)
            self.assertEqual(count, 1)
            db.refresh(sub)
            self.assertEqual(sub.last_forwarded_message_id, new.id)

    def test_summary_dispatch_advances_next_run(self) -> None:
        with _temp_db() as db:
            db.add(CM(direction="INCOMING", status="RECEIVED", channel="EMAIL",
                      procurement_record_id=10, supplier_po_no="PO-1",
                      subject="hi", body="update"))
            db.commit()
            sub = subs.create_pending(
                db, kind="SCHEDULED_SUMMARY", supplier_id=1, procurement_record_id=10,
                supplier_po_no="PO-1", recipient_user_id=5, recipient_email="a@x.com",
                recipient_label="A", created_by_user_id=2, schedule="daily",
            )
            subs.confirm(db, sub.id, now=datetime(2026, 6, 28, 8, 0))
            with patch("app.scheduler.jobs.msg_service.queue_outgoing_message") as qom, \
                 patch("app.scheduler.jobs.mail_send_worker.send_message_now", return_value={"sent": True}), \
                 patch("app.scheduler.jobs.notif.safe", return_value=0):
                qom.return_value = type("M", (), {"id": 99})()
                count = jobs._dispatch_summaries(db, datetime(2026, 6, 28, 9, 5))
            self.assertEqual(count, 1)
            db.refresh(sub)
            self.assertEqual(sub.next_run_at, datetime(2026, 6, 29, 9, 0))
