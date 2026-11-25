"""Staff scope on the staff Communication Hub + customer mails (2026-11-25).

Admins see every PO; manager / user / viewer see only POs they own
(owner_emp_code) plus every PO of a supplier assigned to them. Out-of-scope ids
answer 404. Route functions are called directly on an in-memory SQLite DB.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_staff_scope_hub.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CustomerMail,
    MailHistory,
    ProcurementRecord,
    SupplierMaster,
    User,
)
from app.models.supplier_assignment import SupplierAssignment  # noqa: E402
from app.routers import communication_hub as hub  # noqa: E402
from app.routers import customer_mails as cm  # noqa: E402
from app.services import staff_scope, user_service  # noqa: E402


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


def _po(db, *, po, name, owner, signal="RED"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{po}", material_name="Widget", supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _supplier(db, name):
    s = SupplierMaster(supplier_name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _staff(db, username, role, emp_code=None):
    return user_service.create_user(
        db, email=f"{username}@corp.com", password="x" * 8, role=role,
        emp_code=emp_code, username=username, full_name=username.title(),
    )


def _msg(db, *, name, po, direction="INCOMING", status="RECEIVED", rec_id=None):
    m = CommunicationMessage(
        direction=direction, status=status, supplier_name=name,
        supplier_po_no=po, procurement_record_id=rec_id,
        subject=f"PO {po}", body="hello",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


class HubStaffScopeTests(unittest.TestCase):
    def setUp(self):
        self._cm = _temp_db()
        self.db = self._cm.__enter__()
        db = self.db
        self.acme = _supplier(db, "ACME TOOLS")
        self.beta = _supplier(db, "BETA PARTS")
        self.gamma = _supplier(db, "GAMMA CO")
        self.a1 = _po(db, po="PO-A1", name="ACME TOOLS", owner="E1")
        self.a2 = _po(db, po="PO-A2", name="ACME TOOLS", owner="E2")
        self.b1 = _po(db, po="PO-B1", name="BETA PARTS", owner="E2")
        self.g1 = _po(db, po="PO-G1", name="GAMMA CO", owner="E2")
        self.user = _staff(db, "vijay", Role.USER, emp_code="E1")
        self.admin = _staff(db, "boss", Role.ADMIN)
        # GAMMA is assigned to vijay on the Supplier Assignment page.
        db.add(SupplierAssignment(supplier_id=self.gamma.id, user_id=self.user.id))
        db.commit()
        self.scope = staff_scope.for_user(db, self.user)

    def tearDown(self):
        self._cm.__exit__(None, None, None)

    def test_admin_is_unscoped(self):
        self.assertIsNone(staff_scope.for_user(self.db, self.admin))

    def test_suppliers_list_only_in_scope(self):
        rows = hub.list_suppliers(db=self.db, staff=self.scope)
        names = {r["supplier_name"] for r in rows}
        self.assertEqual(names, {"ACME TOOLS", "GAMMA CO"})
        acme = next(r for r in rows if r["supplier_name"] == "ACME TOOLS")
        self.assertEqual(acme["open_po_count"], 1)  # PO-A2 is someone else's
        all_rows = hub.list_suppliers(db=self.db, staff=None)
        self.assertEqual(len(all_rows), 3)

    def test_purchase_orders_filtered(self):
        acme = hub.pos_by_supplier_name(supplier_name="ACME TOOLS", db=self.db, staff=self.scope)
        self.assertEqual({p["supplier_po_no"] for p in acme}, {"PO-A1"})
        self.assertEqual(
            hub.supplier_pos_by_id(supplier_id=self.beta.id, db=self.db, staff=self.scope), []
        )
        gamma = hub.supplier_pos_by_id(supplier_id=self.gamma.id, db=self.db, staff=self.scope)
        self.assertEqual({p["supplier_po_no"] for p in gamma}, {"PO-G1"})

    def test_thread_404_out_of_scope(self):
        with self.assertRaises(HTTPException) as ctx:
            hub.get_thread(procurement_record_id=self.a2.id, db=self.db, staff=self.scope)
        self.assertEqual(ctx.exception.status_code, 404)
        with self.assertRaises(HTTPException):
            hub.get_thread(supplier_po_no="PO-B1", supplier_name="BETA PARTS",
                           db=self.db, staff=self.scope)
        hub.get_thread(procurement_record_id=self.a1.id, db=self.db, staff=self.scope)
        hub.get_thread(procurement_record_id=self.g1.id, db=self.db, staff=self.scope)
        with self.assertRaises(HTTPException):
            hub.mark_thread_read(procurement_record_id=self.b1.id, db=self.db, staff=self.scope)

    def test_dashboard_counts_scoped(self):
        _msg(self.db, name="ACME TOOLS", po="PO-A1")
        _msg(self.db, name="BETA PARTS", po="PO-B1")
        mine = hub.comm_dashboard(db=self.db, viewer=self.user, staff=self.scope)
        everyone = hub.comm_dashboard(db=self.db, viewer=self.admin, staff=None)
        self.assertEqual(mine["active_pos"], 2)  # PO-A1 + assigned PO-G1
        self.assertEqual(everyone["active_pos"], 4)
        self.assertEqual(mine["active_suppliers"], 2)
        self.assertEqual(mine["unread_inbound"], 1)
        self.assertEqual(everyone["unread_inbound"], 2)

    def test_sent_feed_and_drafts_scoped(self):
        from datetime import datetime

        sent_mine = _msg(self.db, name="ACME TOOLS", po="PO-A1", direction="OUTGOING", status="SENT")
        sent_other = _msg(self.db, name="BETA PARTS", po="PO-B1", direction="OUTGOING", status="SENT")
        for m in (sent_mine, sent_other):
            m.sent_at = datetime.utcnow()
        self.db.commit()
        feed = hub.sent_feed(since=None, limit=20, db=self.db, staff=self.scope)
        self.assertEqual([i["id"] for i in feed["items"]], [sent_mine.id])

        draft_other = _msg(self.db, name="BETA PARTS", po="PO-B1", direction="OUTGOING", status="DRAFT")
        draft_mine = _msg(self.db, name="GAMMA CO", po="PO-G1", direction="OUTGOING", status="DRAFT")
        self.assertEqual(
            [d["id"] for d in hub.list_outbox_drafts(db=self.db, staff=self.scope)], [draft_mine.id]
        )
        with self.assertRaises(HTTPException):
            hub.approve_message(draft_other.id, db=self.db, staff=self.scope)
        with self.assertRaises(HTTPException):
            hub.discard_message(draft_other.id, db=self.db, staff=self.scope)
        self.assertTrue(hub.approve_message(draft_mine.id, db=self.db, staff=self.scope)["ok"])

    def test_write_paths_404_out_of_scope(self):
        with self.assertRaises(HTTPException):
            hub.ai_reply(procurement_record_id=self.b1.id, db=self.db, staff=self.scope)
        with self.assertRaises(HTTPException):
            hub.escalate(procurement_record_id=self.b1.id, db=self.db, staff=self.scope)
        with self.assertRaises(HTTPException):
            hub.get_agent_history(procurement_record_id=self.a2.id, db=self.db, staff=self.scope)
        with self.assertRaises(HTTPException):
            hub.reply_now(
                hub.HubReplyIn(procurement_record_id=self.b1.id, body="hi", send_email=False),
                db=self.db, staff=self.scope,
            )
        ok = hub.reply_now(
            hub.HubReplyIn(procurement_record_id=self.a1.id, body="hi", send_email=False),
            db=self.db, staff=self.scope,
        )
        self.assertTrue(ok["ok"])

    def test_other_mails_need_supplier_in_scope(self):
        _msg(self.db, name="BETA PARTS", po=None)
        self.assertEqual(hub.list_other_mails(supplier_name="BETA PARTS", db=self.db, staff=self.scope), [])
        _msg(self.db, name="GAMMA CO", po=None)
        self.assertEqual(
            len(hub.list_other_mails(supplier_name="GAMMA CO", db=self.db, staff=self.scope)), 1
        )

    def test_direct_calls_without_staff_stay_unscoped(self):
        # eportal_hub reuses these handlers after its own scoping.
        self.assertEqual(len(hub.pos_by_supplier_name(supplier_name="ACME TOOLS", db=self.db)), 2)


class CustomerMailStaffScopeTests(unittest.TestCase):
    def test_list_and_detail_scoped(self):
        with _temp_db() as db:
            _po(db, po="PO-A1", name="ACME TOOLS", owner="E1")
            user = _staff(db, "vijay", Role.USER, emp_code="E1")
            mine = CustomerMail(subject="a", from_email="x@zanvargroup.com", linked_supplier_po_no="PO-A1", mail_type="GENERAL",
                                status="OPEN", priority="MEDIUM")
            named = CustomerMail(subject="b", from_email="x@zanvargroup.com", assigned_to="Vijay", mail_type="GENERAL",
                                 status="OPEN", priority="MEDIUM")
            other = CustomerMail(subject="c", from_email="x@zanvargroup.com", linked_supplier_po_no="PO-ZZ", mail_type="GENERAL",
                                 status="OPEN", priority="MEDIUM")
            db.add_all([mine, named, other])
            db.commit()
            scope = staff_scope.for_user(db, user)

            def ids(staff):
                res = cm.list_customer_mails(
                    db=db, status=None, mail_type=None, assigned_to=None, search=None,
                    scope="customer", limit=100, offset=0, user=user, staff=staff,
                )
                return {i.id for i in res.items}

            self.assertEqual(ids(scope), {mine.id, named.id})
            self.assertEqual(ids(None), {mine.id, named.id, other.id})
            cm.get_customer_mail(mine.id, db=db, user=user, staff=scope)
            with self.assertRaises(HTTPException):
                cm.get_customer_mail(other.id, db=db, user=user, staff=scope)
            with self.assertRaises(HTTPException):
                cm.list_customer_mail_replies(other.id, db=db, user=user, staff=scope)


if __name__ == "__main__":
    unittest.main()
