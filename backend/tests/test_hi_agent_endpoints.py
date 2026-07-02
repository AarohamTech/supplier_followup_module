"""Endpoint-level tests for the HI agent confirm flow (service-call level)."""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401
    AgentSubscription,
    CommunicationMessage,
    HiAgentChatMessage,
    Notification,
    ProcurementRecord,
    User,
)
from app.models.communication_message import CommunicationMessage as CM
from app.models.notification import Notification as Notif
from app.routers import communication_hub as hub
from app.services import agent_subscription_service as subs
from app.services import user_service


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


class ConfirmEndpointTests(unittest.TestCase):
    def test_po_id_thread_persists_and_reuses_chat_context(self) -> None:
        with _temp_db() as db:
            user = user_service.create_user(
                db, email="buyer@co.com", password="password", full_name="Buyer",
                username="buyer", role="user",
            )
            po = ProcurementRecord(
                crm_no="CRM-1", material_name="Widget", supplier_po_no="PO-1",
                supplier_name="ACME",
            )
            db.add(po); db.commit(); db.refresh(po)
            seen_history = []

            def fake_run(*args, **kwargs):
                seen_history.append(kwargs.get("history"))
                return {"reply": "Saved reply", "pending_actions": [], "tools_used": []}

            payload = hub.HubAgentIn(
                message="first question", procurement_record_id=po.id,
                supplier_po_no=po.supplier_po_no,
            )
            with patch("app.routers.communication_hub.hi_agent_service.run", side_effect=fake_run):
                first = hub.run_agent(payload=payload, user=user, db=db)
                payload.message = "follow-up question"
                second = hub.run_agent(payload=payload, user=user, db=db)

            self.assertEqual(first["thread_id"], str(po.id))
            self.assertEqual(len(first["messages"]), 2)
            self.assertEqual(len(second["messages"]), 4)
            self.assertEqual(seen_history[0], [])
            self.assertEqual(
                seen_history[1],
                [
                    {"role": "user", "content": "first question"},
                    {"role": "assistant", "content": "Saved reply"},
                ],
            )

            restored = hub.get_agent_history(procurement_record_id=po.id, db=db)
            self.assertEqual([m["text"] for m in restored["messages"]], [
                "first question", "Saved reply", "follow-up question", "Saved reply",
            ])

    def test_confirm_draft_promotes_and_sends(self) -> None:
        with _temp_db() as db:
            msg = CM(direction="OUTGOING", status="DRAFT", channel="EMAIL",
                     to_emails=["a@x.com"], subject="s", body="b",
                     mail_type="HI_AGENT_SEND")
            db.add(msg); db.commit(); db.refresh(msg)
            sent = {"called": False}

            def fake_send(_db, mid):
                sent["called"] = True
                m = _db.get(CM, mid); m.status = "SENT"; _db.commit()
                return {"sent": True}

            with patch("app.workers.mail_send_worker.send_message_now", side_effect=fake_send):
                out = hub._confirm_action(db, action_type="draft", action_id=msg.id)
            self.assertTrue(sent["called"])
            self.assertTrue(out["ok"])
            db.refresh(msg)
            self.assertEqual(msg.status, "SENT")

    def test_confirm_draft_notifies_internal_recipient(self) -> None:
        with _temp_db() as db:
            anjali = user_service.create_user(
                db, email="anjali@co.com", password="x", full_name="Anjali",
                username="anjali", role="user",
            )
            msg = CM(direction="OUTGOING", status="DRAFT", channel="EMAIL",
                     to_emails=["anjali@co.com"], subject="FYI PO-1", body="see thread",
                     supplier_po_no="PO-1", mail_type="HI_AGENT_SEND")
            db.add(msg); db.commit(); db.refresh(msg)
            with patch("app.workers.mail_send_worker.send_message_now",
                       return_value={"sent": True}):
                out = hub._confirm_action(db, action_type="draft", action_id=msg.id)
            self.assertTrue(out["notified"])
            notes = db.query(Notif).filter(Notif.user_id == anjali.id).all()
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0].type, "HI_MESSAGE")

    def test_confirm_subscription_activates(self) -> None:
        with _temp_db() as db:
            sub = subs.create_pending(
                db, kind="FOLLOWUP", supplier_id=1, procurement_record_id=10,
                supplier_po_no="PO-1", recipient_user_id=5, recipient_email="a@x.com",
                recipient_label="A", created_by_user_id=2,
            )
            out = hub._confirm_action(db, action_type="subscription", action_id=sub.id)
            self.assertTrue(out["ok"])
            db.refresh(sub)
            self.assertEqual(sub.status, "ACTIVE")

    def test_confirm_rejects_non_draft_message(self) -> None:
        with _temp_db() as db:
            msg = CM(direction="OUTGOING", status="SENT", channel="EMAIL",
                     to_emails=["a@x.com"], subject="s", body="b")
            db.add(msg); db.commit(); db.refresh(msg)
            out = hub._confirm_action(db, action_type="draft", action_id=msg.id)
            self.assertFalse(out["ok"])
