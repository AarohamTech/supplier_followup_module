"""Non-PO "Other Mails" surfacing + reply threading.

DB-backed with in-memory SQLite (production data untouched). Mirrors the
patterns in test_hub_unread.py / test_eportal_hub_scope.py: call the route
functions directly with a constructed Session (+ User for the employee hub).
"""
from __future__ import annotations

import itertools
import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_other_mails.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    CustomerMail,
    MailHistory,
    Notification,
    ProcurementRecord,
    SupplierMaster,
    User,
)
from app.routers import communication_hub as hub  # noqa: E402
from app.routers import eportal_hub as ehub  # noqa: E402
from app.services import communication_message_service as svc  # noqa: E402
from app.services import hi_agent_tools  # noqa: E402
from app.services import user_service  # noqa: E402


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


_clock = itertools.count()


def _ts() -> datetime:
    # Strictly increasing timestamps so "latest" ordering is deterministic.
    return datetime(2026, 1, 1) + timedelta(minutes=next(_clock))


def _supplier(db, name):
    s = SupplierMaster(supplier_name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _po(db, *, po, name, owner=None, signal="RED"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{po}", material_name="Widget", supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _incoming(db, *, name, subject, po=None, supplier_id=None, read=False, uid=None):
    m = CommunicationMessage(
        direction="INCOMING", status="RECEIVED", channel="EMAIL",
        supplier_id=supplier_id, supplier_name=name, supplier_po_no=po,
        subject=subject, body="please advise", sender_email="vendor@acme.com",
        message_uid=uid, read_at=_ts() if read else None, created_at=_ts(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _emp(db, emp_code):
    return user_service.create_user(
        db, email=f"{emp_code}@corp.com", password="x" * 8, role=Role.EMPLOYEE,
        emp_code=emp_code, username=emp_code,
    )


class SubjectHelperTests(unittest.TestCase):
    def test_normalize_strips_reply_prefixes_and_casing(self):
        self.assertEqual(svc.normalize_subject("Re: Quotation request"), "quotation request")
        self.assertEqual(svc.normalize_subject("RE: re: Fwd: Hello  World"), "hello world")
        self.assertEqual(svc.normalize_subject("  Plain  "), "plain")
        self.assertEqual(svc.normalize_subject(None), "")

    def test_reply_subject_adds_prefix_once_and_keeps_case(self):
        self.assertEqual(svc.reply_subject("Quotation"), "Re: Quotation")
        self.assertEqual(svc.reply_subject("Re: Quotation"), "Re: Quotation")
        self.assertEqual(svc.reply_subject("RE: Quotation"), "RE: Quotation")


class AdminOtherMailsTests(unittest.TestCase):
    def test_non_po_count_surfaced_on_suppliers(self):
        with _temp_db() as db:
            s = _supplier(db, "ACME TOOLS")
            _incoming(db, name="ACME TOOLS", subject="Quotation request", supplier_id=s.id)
            _incoming(db, name="ACME TOOLS", subject="Payment terms", supplier_id=s.id)
            _incoming(db, name="ACME TOOLS", subject="PO update", po="ACME-1", supplier_id=s.id)
            rows = {r["supplier_name"]: r for r in hub.list_suppliers(db=db)}
            self.assertEqual(rows["ACME TOOLS"]["non_po_count"], 2)

    def test_other_mails_grouped_by_subject(self):
        with _temp_db() as db:
            s = _supplier(db, "ACME TOOLS")
            _incoming(db, name="ACME TOOLS", subject="Quotation request", supplier_id=s.id)
            _incoming(db, name="ACME TOOLS", subject="Re: Quotation request", supplier_id=s.id)
            _incoming(db, name="ACME TOOLS", subject="Payment terms", supplier_id=s.id, read=True)
            # A PO mail must NOT appear in Other Mails.
            _incoming(db, name="ACME TOOLS", subject="PO update", po="ACME-1", supplier_id=s.id)

            threads = hub.list_other_mails(supplier_id=s.id, supplier_name="ACME TOOLS", db=db)
            by_key = {t["thread_key"]: t for t in threads}
            self.assertEqual(set(by_key), {"quotation request", "payment terms"})
            self.assertEqual(by_key["quotation request"]["message_count"], 2)
            self.assertEqual(by_key["quotation request"]["unread_inbound"], 2)
            self.assertEqual(by_key["payment terms"]["unread_inbound"], 0)

    def test_thread_non_po_returns_grouped_messages(self):
        with _temp_db() as db:
            s = _supplier(db, "ACME TOOLS")
            _incoming(db, name="ACME TOOLS", subject="Quotation request", supplier_id=s.id)
            _incoming(db, name="ACME TOOLS", subject="Re: Quotation request", supplier_id=s.id)
            thread = hub.get_thread(
                supplier_id=s.id, supplier_name="ACME TOOLS",
                non_po_subject="quotation request", db=db,
            )
            self.assertIsNone(thread["supplier_po_no"])
            self.assertIsNone(thread["procurement_record_id"])
            self.assertEqual(len(thread["messages"]), 2)

    def test_mark_read_non_po_clears_unread(self):
        with _temp_db() as db:
            s = _supplier(db, "ACME TOOLS")
            _incoming(db, name="ACME TOOLS", subject="Quotation request", supplier_id=s.id)
            _incoming(db, name="ACME TOOLS", subject="Re: Quotation request", supplier_id=s.id)
            out = hub.mark_thread_read(
                supplier_id=s.id, supplier_name="ACME TOOLS",
                non_po_subject="quotation request", db=db,
            )
            self.assertEqual(out["marked"], 2)
            threads = {t["thread_key"]: t for t in
                       hub.list_other_mails(supplier_id=s.id, supplier_name="ACME TOOLS", db=db)}
            self.assertEqual(threads["quotation request"]["unread_inbound"], 0)

    def test_reply_threads_po_mail_via_in_reply_to(self):
        with _temp_db() as db:
            s = _supplier(db, "ACME TOOLS")
            _po(db, po="ACME-1", name="ACME TOOLS")
            _incoming(db, name="ACME TOOLS", subject="PO update", po="ACME-1",
                      supplier_id=s.id, uid="<orig-po@vendor>")
            res = hub.reply_now(
                hub.HubReplyIn(
                    supplier_po_no="ACME-1", supplier_name="ACME TOOLS",
                    body="thanks", send_email=False,
                ),
                db=db,
            )
            msg = db.get(CommunicationMessage, res["message_id"])
            self.assertEqual(msg.in_reply_to, "<orig-po@vendor>")

    def test_reply_threads_non_po_mail_via_in_reply_to(self):
        with _temp_db() as db:
            s = _supplier(db, "ACME TOOLS")
            _incoming(db, name="ACME TOOLS", subject="Quotation request",
                      supplier_id=s.id, uid="<orig-q@vendor>")
            res = hub.reply_now(
                hub.HubReplyIn(
                    supplier_id=s.id, supplier_name="ACME TOOLS",
                    non_po_subject="quotation request", body="here you go",
                    send_email=False,
                ),
                db=db,
            )
            msg = db.get(CommunicationMessage, res["message_id"])
            self.assertEqual(msg.in_reply_to, "<orig-q@vendor>")
            self.assertIsNone(msg.supplier_po_no)
            self.assertTrue((msg.subject or "").lower().startswith("re:"))


class EportalOtherMailsScopeTests(unittest.TestCase):
    def test_other_mails_scoped_to_owned_supplier(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1")
            _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2")
            _incoming(db, name="ACME TOOLS", subject="Quotation request")
            _incoming(db, name="BETA PARTS", subject="Invoice query")

            owned = ehub.list_other_mails(supplier_name="ACME TOOLS", user=emp1, db=db)
            self.assertEqual({t["thread_key"] for t in owned}, {"quotation request"})
            # Supplier the employee does not own → nothing (no existence leak).
            self.assertEqual(ehub.list_other_mails(supplier_name="BETA PARTS", user=emp1, db=db), [])

    def test_thread_non_po_foreign_404(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1")
            _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2")
            _incoming(db, name="BETA PARTS", subject="Invoice query")
            with self.assertRaises(HTTPException) as cm:
                ehub.get_thread(supplier_name="BETA PARTS", non_po_subject="invoice query",
                                user=emp1, db=db)
            self.assertEqual(cm.exception.status_code, 404)

    def test_reply_non_po_foreign_404(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2")
            payload = hub.HubReplyIn(supplier_name="BETA PARTS",
                                     non_po_subject="invoice query", body="hi", send_email=False)
            with self.assertRaises(HTTPException) as cm:
                ehub.reply_now(payload, user=emp1, db=db)
            self.assertEqual(cm.exception.status_code, 404)

    def test_reply_non_po_owned_ok(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            s = _supplier(db, "ACME TOOLS")
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1")
            _incoming(db, name="ACME TOOLS", subject="Quotation request",
                      supplier_id=s.id, uid="<q@vendor>")
            res = ehub.reply_now(
                hub.HubReplyIn(supplier_id=s.id, supplier_name="ACME TOOLS",
                               non_po_subject="quotation request", body="ok", send_email=False),
                user=emp1, db=db,
            )
            self.assertTrue(res["ok"])
            self.assertEqual(db.get(CommunicationMessage, res["message_id"]).in_reply_to, "<q@vendor>")


class HiAgentReplyThreadingTests(unittest.TestCase):
    """A HI-agent *reply* draft must thread (In-Reply-To); a one-time send must not."""

    def test_supplier_reply_draft_threads(self):
        with _temp_db() as db:
            s = _supplier(db, "ACME TOOLS")
            rec = _po(db, po="ACME-1", name="ACME TOOLS")
            _incoming(db, name="ACME TOOLS", subject="PO update", po="ACME-1",
                      supplier_id=s.id, uid="<inb@vendor>")
            ctx = hi_agent_tools.ToolContext(
                db=db, user=None, supplier_id=s.id,
                procurement_record_id=rec.id, supplier_po_no="ACME-1",
            )
            with patch.object(hi_agent_tools.ai_service, "is_enabled", return_value=False):
                out = hi_agent_tools.tool_draft_reply(ctx, {"instruction": "ok"})
            msg = db.get(CommunicationMessage, out["message_id"])
            self.assertEqual(msg.in_reply_to, "<inb@vendor>")
            self.assertEqual(msg.status, "DRAFT")

    def test_customer_reply_draft_threads(self):
        with _temp_db() as db:
            cm = CustomerMail(subject="Critical material", body="urgent",
                              from_email="x@cust.com", message_uid="<cust@x>")
            db.add(cm)
            db.commit()
            db.refresh(cm)
            ctx = hi_agent_tools.ToolContext(
                db=db, user=None, supplier_id=None, procurement_record_id=None,
                supplier_po_no=None, customer_mail_id=cm.id,
                customer_email="x@cust.com", customer_name="X",
            )
            with patch.object(hi_agent_tools.ai_service, "is_enabled", return_value=False):
                out = hi_agent_tools.tool_draft_reply(ctx, {"instruction": "thanks"})
            msg = db.get(CommunicationMessage, out["message_id"])
            self.assertEqual(msg.in_reply_to, "<cust@x>")

if __name__ == "__main__":
    unittest.main()
