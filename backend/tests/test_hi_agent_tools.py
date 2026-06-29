"""Tests for HI-agent tool functions."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (  # noqa: F401
    AgentSubscription, CommunicationMessage, ProcurementRecord, SupplierEmail, User,
)
from app.models.agent_subscription import AgentSubscription as Sub
from app.models.communication_message import CommunicationMessage as CM
from app.models.customer_mail import CustomerMail
from app.services import hi_agent_tools as tools
from app.services import task_assignment_service as assign
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


def _seed_thread(db):
    db.add(CM(
        direction="OUTGOING", status="SENT", channel="EMAIL",
        procurement_record_id=10, supplier_po_no="PO-1",
        subject="Follow-up PO-1", body="Please confirm dispatch date.",
    ))
    db.add(CM(
        direction="INCOMING", status="RECEIVED", channel="EMAIL",
        procurement_record_id=10, supplier_po_no="PO-1",
        subject="Re: Follow-up PO-1", body="Dispatching on 5 July.",
    ))
    db.commit()


def _ctx(db):
    return tools.ToolContext(
        db=db, user=None, supplier_id=1, procurement_record_id=10, supplier_po_no="PO-1",
    )


class ReadToolTests(unittest.TestCase):
    def test_gather_thread_returns_messages_in_order(self) -> None:
        with _temp_db() as db:
            _seed_thread(db)
            rows = tools.gather_thread(db, 10, "PO-1")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["direction"], "OUTGOING")
            self.assertIn("dispatch", rows[0]["body"].lower())

    def test_read_thread_tool_reports_count(self) -> None:
        with _temp_db() as db:
            _seed_thread(db)
            out = tools.tool_read_thread(_ctx(db), {})
            self.assertEqual(out["message_count"], 2)
            self.assertIn("5 July", out["transcript"])

    def test_summarize_falls_back_when_llm_disabled(self) -> None:
        with _temp_db() as db:
            _seed_thread(db)
            out = tools.tool_summarize(_ctx(db), {})
            self.assertIn("summary", out)
            self.assertTrue(out["summary"])

    def test_explain_signal_uses_po_record(self) -> None:
        with _temp_db() as db:
            db.add(ProcurementRecord(
                id=10, crm_no="C1", material_name="PIN", supplier_name="Acme",
                supplier_po_no="PO-1", signal="RED",
            ))
            _seed_thread(db)
            out = tools.tool_explain_signal(_ctx(db), {})
            self.assertIn("RED", out["explanation"])


class DraftToolTests(unittest.TestCase):
    def test_resolve_internal_user_by_username(self) -> None:
        with _temp_db() as db:
            user_service.create_user(
                db, email="anjali@co.com", password="x", full_name="Anjali",
                username="anjali", role="user",
            )
            r = tools.resolve_recipient(db, "@anjali", allow_supplier=False)
            self.assertTrue(r["found"])
            self.assertEqual(r["kind"], "user")
            self.assertEqual(r["email"], "anjali@co.com")

    def test_subscription_recipient_rejects_supplier(self) -> None:
        with _temp_db() as db:
            db.add(SupplierEmail(
                supplier_id=1, supplier_name="Acme", is_active=True,
                to_emails=["sales@acme.com"],
            ))
            db.commit()
            r = tools.resolve_recipient(db, "@Acme", allow_supplier=False)
            self.assertFalse(r["found"])

    def test_draft_email_creates_draft_and_does_not_send(self) -> None:
        with _temp_db() as db:
            user_service.create_user(
                db, email="anjali@co.com", password="x", full_name="Anjali",
                username="anjali", role="user",
            )
            ctx = _ctx(db)
            out = tools.tool_draft_email(ctx, {
                "mention": "@anjali", "subject": "FYI PO-1", "body": "See thread.",
            })
            self.assertTrue(out["drafted"])
            msg = db.get(CM, out["message_id"])
            self.assertEqual(msg.status, "DRAFT")
            self.assertEqual(msg.direction, "OUTGOING")
            self.assertIn("anjali@co.com", msg.to_emails)
            self.assertEqual(len(ctx.pending_actions), 1)
            self.assertEqual(ctx.pending_actions[0]["type"], "draft")

    def test_draft_email_unknown_recipient_returns_error_no_draft(self) -> None:
        with _temp_db() as db:
            ctx = _ctx(db)
            out = tools.tool_draft_email(ctx, {
                "mention": "@nobody", "subject": "x", "body": "y",
            })
            self.assertFalse(out.get("drafted"))
            self.assertEqual(db.query(CM).count(), 0)


class SubscriptionToolTests(unittest.TestCase):
    def test_create_followup_subscription_internal_only(self) -> None:
        with _temp_db() as db:
            user_service.create_user(
                db, email="anjali@co.com", password="x", full_name="Anjali",
                username="anjali", role="user",
            )
            ctx = _ctx(db)
            out = tools.tool_create_subscription(ctx, {
                "kind": "FOLLOWUP", "mention": "@anjali",
            })
            self.assertTrue(out["created"])
            sub = db.get(Sub, out["subscription_id"])
            self.assertEqual(sub.status, "PENDING")
            self.assertEqual(sub.kind, "FOLLOWUP")
            self.assertEqual(ctx.pending_actions[-1]["type"], "subscription")

    def test_subscription_to_supplier_is_rejected(self) -> None:
        with _temp_db() as db:
            db.add(SupplierEmail(
                supplier_id=1, supplier_name="Acme", is_active=True,
                to_emails=["sales@acme.com"],
            ))
            db.commit()
            ctx = _ctx(db)
            out = tools.tool_create_subscription(ctx, {
                "kind": "FOLLOWUP", "mention": "@Acme",
            })
            self.assertFalse(out["created"])
            self.assertEqual(db.query(Sub).count(), 0)

    def test_executor_dispatches_by_name(self) -> None:
        with _temp_db() as db:
            _seed_thread(db)
            ex = tools.make_executor(_ctx(db))
            out = ex("read_thread", {})
            self.assertEqual(out["message_count"], 2)
            self.assertIn("error", ex("unknown_tool", {}))

class CustomerMentionTests(unittest.TestCase):
    def test_resolve_customer_by_email(self) -> None:
        with _temp_db() as db:
            db.add(CustomerMail(from_email="buyer@acme-customer.com", customer_name="Acme Buyer"))
            db.commit()
            r = tools.resolve_recipient(db, "@buyer@acme-customer.com", allow_supplier=True)
            self.assertTrue(r["found"])
            self.assertEqual(r["kind"], "customer")
            self.assertEqual(r["email"], "buyer@acme-customer.com")

    def test_resolve_customer_not_allowed_when_internal_only(self) -> None:
        with _temp_db() as db:
            db.add(CustomerMail(from_email="buyer@acme-customer.com", customer_name="Acme Buyer"))
            db.commit()
            r = tools.resolve_recipient(db, "@buyer@acme-customer.com", allow_supplier=False)
            self.assertFalse(r["found"])

    def test_list_mention_targets_includes_customers(self) -> None:
        with _temp_db() as db:
            user_service.create_user(
                db, email="staff@co.com", password="x", full_name="Staff One",
                username="staff", role="user",
            )
            db.add(CustomerMail(from_email="buyer@acme-customer.com", customer_name="Acme Buyer"))
            db.commit()
            rows = assign.list_mention_targets(db)
            types = {r["type"] for r in rows}
            self.assertIn("customer", types)
            cust = next(r for r in rows if r["type"] == "customer")
            self.assertEqual(cust["email"], "buyer@acme-customer.com")
            self.assertEqual(cust["id"], 0)


class SchemaTests(unittest.TestCase):
    def test_tools_schema_lists_all_tools(self) -> None:
        names = {t["function"]["name"] for t in tools.TOOLS}
        self.assertEqual(names, {
            "read_thread", "summarize_thread", "extract_action_items",
            "explain_signal", "resolve_recipient", "draft_email", "draft_reply",
            "create_subscription", "list_subscriptions",
        })
