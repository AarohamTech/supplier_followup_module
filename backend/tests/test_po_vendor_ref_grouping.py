"""Hub thread identity = (supplier, vendor PO ref), not the CRM counter.

`supplier_po_no` (CRM PoNo) is a customer-order-side counter: one vendor PO
document (`po_short_ref`, e.g. 2627-001766 — the number the supplier knows and
the Orders page shows as "Vendor PO No.") can be split across up to 7 counters,
and one counter can carry two different vendor POs. Grouping hub threads by the
counter therefore scattered one vendor PO's mails over several threads and
merged unrelated vendor POs into one — "mails conflicting with each other".

These tests pin the fix: threads bucket by po_short_ref when present, records
without a ref join their counter's ref-group when that is unambiguous, and
message matching follows the whole group (all its counters + record ids).

Uses the in-memory SQLite pattern: call functions directly, prod untouched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_po_vendor_ref.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    MailHistory,
    ProcurementRecord,
    SupplierMaster,
)
from app.routers import communication_hub as hub  # noqa: E402
from app.routers import eportal_hub  # noqa: E402
from app.services import po_followup_service  # noqa: E402


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


TAEGUTEC = "TAEGUTEC INDIA PRIVATE LIMITED"


def _rec(db, *, name=TAEGUTEC, po, ref=None, owner=None, material="Widget"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{po}-{material[:6]}", material_name=material,
        supplier_po_no=po, po_short_ref=ref, supplier_name=name,
        owner_emp_code=owner, signal="RED",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _incoming(db, *, name=TAEGUTEC, po, rec_id=None, subject="reply", uid=None):
    m = CommunicationMessage(
        direction="INCOMING", status="RECEIVED", channel="EMAIL",
        supplier_name=name, supplier_po_no=po, procurement_record_id=rec_id,
        subject=subject, body="hi", message_uid=uid,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


class PoListGroupingTests(unittest.TestCase):
    def test_list_merges_vendor_po_split_across_counters(self):
        # One vendor PO 2627-001766 was ingested under two CRM counters.
        with _temp_db() as db:
            a = _rec(db, po="000609", ref="2627-001766", material="Insert A")
            b = _rec(db, po="000694", ref="2627-001766", material="Insert B")

            pos = hub._pos_for_supplier(db, None, TAEGUTEC)
            self.assertEqual(len(pos), 1)
            group = pos[0]
            self.assertEqual(group["po_ref"], "2627-001766")
            self.assertEqual(
                sorted(group["procurement_record_ids"]), sorted([a.id, b.id])
            )
            self.assertEqual(sorted(group["supplier_po_nos"]), ["000609", "000694"])

    def test_list_splits_shared_counter_by_vendor_ref(self):
        # Counter #001114 carries two different vendor POs.
        with _temp_db() as db:
            x = _rec(db, po="001114", ref="2627-002527", material="Mat X")
            y = _rec(db, po="001114", ref="2627-002540", material="Mat Y")

            pos = hub._pos_for_supplier(db, None, TAEGUTEC)
            self.assertEqual(len(pos), 2)
            by_ref = {p["po_ref"]: p for p in pos}
            self.assertEqual(
                set(by_ref), {"2627-002527", "2627-002540"}
            )
            self.assertEqual(by_ref["2627-002527"]["procurement_record_ids"], [x.id])
            self.assertEqual(by_ref["2627-002540"]["procurement_record_ids"], [y.id])

    def test_null_ref_line_joins_unambiguous_counter_group(self):
        # A line without a ref joins its counter's group when the counter has
        # exactly one known vendor ref.
        with _temp_db() as db:
            a = _rec(db, po="000303", ref="2627-000768", material="Mat A")
            b = _rec(db, po="000303", ref=None, material="Mat B")

            pos = hub._pos_for_supplier(db, None, TAEGUTEC)
            self.assertEqual(len(pos), 1)
            self.assertEqual(pos[0]["po_ref"], "2627-000768")
            self.assertEqual(
                sorted(pos[0]["procurement_record_ids"]), sorted([a.id, b.id])
            )

    def test_null_ref_lines_of_ambiguous_counter_stay_counter_keyed(self):
        # Counter has two refs AND ref-less lines: the ref-less lines cannot be
        # attributed, so they stay in a counter-keyed group of their own.
        with _temp_db() as db:
            _rec(db, po="004171", ref="2627-002112", material="M1")
            _rec(db, po="004171", ref="2627-002114", material="M2")
            n = _rec(db, po="004171", ref=None, material="M3")

            pos = hub._pos_for_supplier(db, None, TAEGUTEC)
            self.assertEqual(len(pos), 3)
            null_groups = [p for p in pos if p["po_ref"] is None]
            self.assertEqual(len(null_groups), 1)
            self.assertEqual(null_groups[0]["procurement_record_ids"], [n.id])

    def test_unread_badge_follows_record_link_on_shared_counter(self):
        # A reply explicitly linked to one vendor PO's record must not light up
        # the other vendor PO sharing the counter.
        with _temp_db() as db:
            x = _rec(db, po="001114", ref="2627-002527", material="Mat X")
            _rec(db, po="001114", ref="2627-002540", material="Mat Y")
            _incoming(db, po="001114", rec_id=x.id)

            pos = hub._pos_for_supplier(db, None, TAEGUTEC)
            by_ref = {p["po_ref"]: p for p in pos}
            self.assertEqual(by_ref["2627-002527"]["unread_inbound"], 1)
            self.assertEqual(by_ref["2627-002540"]["unread_inbound"], 0)


class ThreadScopeTests(unittest.TestCase):
    def test_thread_spans_counters_of_same_vendor_po(self):
        with _temp_db() as db:
            a = _rec(db, po="000609", ref="2627-001766", material="Insert A")
            _rec(db, po="000694", ref="2627-001766", material="Insert B")
            _incoming(db, po="000609", subject="reply on counter 609")
            _incoming(db, po="000694", subject="reply on counter 694")

            thread = hub.get_thread(procurement_record_id=a.id, db=db)
            subjects = {m["subject"] for m in thread["messages"]}
            self.assertIn("reply on counter 609", subjects)
            self.assertIn("reply on counter 694", subjects)
            self.assertEqual(thread["po_ref"], "2627-001766")

    def test_thread_excludes_record_linked_mail_of_other_ref_on_shared_counter(self):
        with _temp_db() as db:
            x = _rec(db, po="001114", ref="2627-002527", material="Mat X")
            y = _rec(db, po="001114", ref="2627-002540", material="Mat Y")
            _incoming(db, po="001114", rec_id=y.id, subject="for the other PO")

            thread_x = hub.get_thread(procurement_record_id=x.id, db=db)
            self.assertNotIn(
                "for the other PO", {m["subject"] for m in thread_x["messages"]}
            )
            thread_y = hub.get_thread(procurement_record_id=y.id, db=db)
            self.assertIn(
                "for the other PO", {m["subject"] for m in thread_y["messages"]}
            )

    def test_mark_read_clears_whole_vendor_po_group(self):
        with _temp_db() as db:
            a = _rec(db, po="000609", ref="2627-001766", material="Insert A")
            _rec(db, po="000694", ref="2627-001766", material="Insert B")
            m1 = _incoming(db, po="000609")
            m2 = _incoming(db, po="000694")
            other = _incoming(db, name="MLA SALES CORPORATION", po="000609")

            hub.mark_thread_read(
                supplier_po_no="000609", procurement_record_id=a.id, db=db
            )
            db.refresh(m1)
            db.refresh(m2)
            db.refresh(other)
            self.assertIsNotNone(m1.read_at)
            self.assertIsNotNone(m2.read_at)
            self.assertIsNone(other.read_at)

    def test_reply_uid_found_across_group_counters(self):
        with _temp_db() as db:
            a = _rec(db, po="000609", ref="2627-001766", material="Insert A")
            _rec(db, po="000694", ref="2627-001766", material="Insert B")
            _incoming(db, po="000694", uid="<latest@mail>")

            uid = hub._latest_incoming_message_uid(
                db,
                supplier_po_no="000609",
                procurement_record_id=a.id,
                supplier_name=TAEGUTEC,
            )
            self.assertEqual(uid, "<latest@mail>")


class EportalScopeTests(unittest.TestCase):
    def test_my_pos_includes_group_when_any_counter_owned(self):
        with _temp_db() as db:
            _rec(db, po="000609", ref="2627-001766", owner="EMP1", material="A")
            _rec(db, po="000694", ref="2627-001766", material="B")
            _rec(db, po="000653", ref="2627-003013", material="C")  # not owned

            from app.core.roles import Role
            from app.services import user_service

            emp = user_service.create_user(
                db, email="emp1@corp.com", password="x" * 8, role=Role.EMPLOYEE,
                emp_code="EMP1", username="emp1",
            )
            pos = eportal_hub.list_pos(supplier_name=TAEGUTEC, user=emp, db=db)
            self.assertEqual(len(pos), 1)
            self.assertEqual(pos[0]["po_ref"], "2627-001766")


if __name__ == "__main__":
    unittest.main()
