"""Cross-supplier isolation for the recycled CRM PO counter.

`supplier_po_no` (CRM PoNo) is a recycled counter shared across suppliers —
e.g. MLA, TAEGUTEC, ISCAR and KYOCERA all have a PO "001249". A PO is only
identified by the (supplier_name, supplier_po_no) pair; the supplier-facing
document number is `po_short_ref` (CRM PoShortRefTrnNo, e.g. 2627-001703).

These tests pin the fixes for the bug where TAEGUTEC's follow-up mail showed
inside MLA's PO #001249 thread in the Communication Hub.

Uses the in-memory SQLite pattern: call functions directly, prod untouched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_po_collision.sqlite")

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
from app.services import communication_message_service as msg_service  # noqa: E402
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


SHARED_PO = "001249"


def _rec(db, *, name, po=SHARED_PO, ref=None, owner=None, material="Widget"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{name[:4]}-{po}", material_name=material,
        supplier_po_no=po, po_short_ref=ref, supplier_name=name,
        owner_emp_code=owner, signal="RED",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _incoming(db, *, name, po=SHARED_PO, subject="reply", body="hi", uid=None):
    m = CommunicationMessage(
        direction="INCOMING", status="RECEIVED", channel="EMAIL",
        supplier_name=name, supplier_po_no=po, subject=subject, body=body,
        message_uid=uid,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


class ThreadIsolationTests(unittest.TestCase):
    def test_thread_excludes_other_suppliers_same_counter(self):
        with _temp_db() as db:
            mla = _rec(db, name="MLA SALES CORPORATION", ref="2627-001708")
            _rec(db, name="TAEGUTEC INDIA PRIVATE LIMITED", ref="2627-001703")
            _incoming(db, name="TAEGUTEC INDIA PRIVATE LIMITED", subject="Taegutec reply")
            _incoming(db, name="MLA SALES CORPORATION", subject="MLA reply")

            thread = hub.get_thread(procurement_record_id=mla.id, db=db)
            subjects = {m["subject"] for m in thread["messages"]}
            self.assertIn("MLA reply", subjects)
            self.assertNotIn("Taegutec reply", subjects)
            # The thread exposes the supplier-facing document number.
            self.assertEqual(thread["po_ref"], "2627-001708")

    def test_mark_read_does_not_touch_other_supplier(self):
        with _temp_db() as db:
            mla = _rec(db, name="MLA SALES CORPORATION", ref="2627-001708")
            _rec(db, name="TAEGUTEC INDIA PRIVATE LIMITED", ref="2627-001703")
            other = _incoming(db, name="TAEGUTEC INDIA PRIVATE LIMITED")
            mine = _incoming(db, name="MLA SALES CORPORATION")

            hub.mark_thread_read(
                supplier_po_no=SHARED_PO, procurement_record_id=mla.id, db=db
            )
            db.refresh(mine)
            db.refresh(other)
            self.assertIsNotNone(mine.read_at)
            self.assertIsNone(other.read_at)

    def test_po_list_unread_badge_not_inflated_by_other_supplier(self):
        with _temp_db() as db:
            _rec(db, name="MLA SALES CORPORATION", ref="2627-001708")
            _rec(db, name="TAEGUTEC INDIA PRIVATE LIMITED", ref="2627-001703")
            _incoming(db, name="TAEGUTEC INDIA PRIVATE LIMITED")

            pos = hub._pos_for_supplier(db, None, "MLA SALES CORPORATION")
            self.assertEqual(len(pos), 1)
            self.assertEqual(pos[0]["unread_inbound"], 0)
            self.assertEqual(pos[0]["po_ref"], "2627-001708")

    def test_reply_threading_uid_scoped_to_supplier(self):
        with _temp_db() as db:
            _incoming(
                db, name="TAEGUTEC INDIA PRIVATE LIMITED", uid="<taegutec@mail>"
            )
            _incoming(db, name="MLA SALES CORPORATION", uid="<mla@mail>")
            uid = hub._latest_incoming_message_uid(
                db,
                supplier_po_no=SHARED_PO,
                supplier_name="MLA SALES CORPORATION",
            )
            self.assertEqual(uid, "<mla@mail>")


class GroupPayloadTests(unittest.TestCase):
    def test_group_payload_carries_po_ref(self):
        with _temp_db() as db:
            _rec(db, name="TAEGUTEC INDIA PRIVATE LIMITED", ref="2627-001703")
            group = po_followup_service.get_po_group(
                db, "TAEGUTEC INDIA PRIVATE LIMITED", SHARED_PO
            )
            self.assertEqual(group["po_ref"], "2627-001703")


class ReplyMatchingTests(unittest.TestCase):
    def test_short_ref_hint_resolves_correct_supplier(self):
        with _temp_db() as db:
            _rec(db, name="MLA SALES CORPORATION", ref="2627-001708")
            tae = _rec(db, name="TAEGUTEC INDIA PRIVATE LIMITED", ref="2627-001703")
            # The parser captured the supplier's own document number.
            rec = msg_service.find_procurement_record(
                db, "2627-001703", "Re: your PO", "we will dispatch soon",
                supplier_name="TAEGUTEC INDIA PRIVATE LIMITED",
            )
            self.assertIsNotNone(rec)
            self.assertEqual(rec.id, tae.id)

    def test_counter_match_scoped_to_sender_supplier(self):
        with _temp_db() as db:
            _rec(db, name="MLA SALES CORPORATION", ref="2627-001708")
            tae = _rec(db, name="TAEGUTEC INDIA PRIVATE LIMITED", ref="2627-001703")
            rec = msg_service.find_procurement_record(
                db, SHARED_PO, "Re: PO", "status update",
                supplier_name="TAEGUTEC INDIA PRIVATE LIMITED",
            )
            self.assertEqual(rec.id, tae.id)

    def test_body_scan_prefers_short_ref_over_recycled_counter(self):
        with _temp_db() as db:
            # A different supplier owns counter "001703" — the naive token scan
            # used to link the reply there via the "-001703" substring.
            _rec(db, name="MLA SALES CORPORATION", po="001703", ref="2627-009999")
            tae = _rec(
                db, name="TAEGUTEC INDIA PRIVATE LIMITED",
                po=SHARED_PO, ref="2627-001703",
            )
            rec = msg_service.find_procurement_record(
                db, None, "Dispatch update", "Regarding PO No. 2627-001703 qty 10",
            )
            self.assertIsNotNone(rec)
            self.assertEqual(rec.id, tae.id)


class EportalPairScopeTests(unittest.TestCase):
    def test_owning_one_suppliers_counter_does_not_grant_anothers(self):
        with _temp_db() as db:
            mine = _rec(db, name="MLA SALES CORPORATION", ref="2627-001708", owner="EMP1")
            other = _rec(
                db, name="TAEGUTEC INDIA PRIVATE LIMITED", ref="2627-001703"
            )
            self.assertTrue(
                eportal_hub._po_in_scope(
                    db, "EMP1", SHARED_PO, "MLA SALES CORPORATION"
                )
            )
            self.assertFalse(
                eportal_hub._po_in_scope(
                    db, "EMP1", SHARED_PO, "TAEGUTEC INDIA PRIVATE LIMITED"
                )
            )
            # Record-level scope: the other supplier's record with the same
            # counter must NOT resolve as in-scope.
            self.assertIsNotNone(
                eportal_hub._record_in_scope(db, "EMP1", mine.id)
            )
            self.assertIsNone(
                eportal_hub._record_in_scope(db, "EMP1", other.id)
            )

    def test_dashboard_unread_counts_pairs_only(self):
        with _temp_db() as db:
            _rec(db, name="MLA SALES CORPORATION", ref="2627-001708", owner="EMP1")
            _rec(db, name="TAEGUTEC INDIA PRIVATE LIMITED", ref="2627-001703")
            _incoming(db, name="TAEGUTEC INDIA PRIVATE LIMITED")

            from app.core.roles import Role
            from app.services import user_service

            emp = user_service.create_user(
                db, email="emp1@corp.com", password="x" * 8, role=Role.EMPLOYEE,
                emp_code="EMP1", username="emp1",
            )
            dash = eportal_hub.dashboard(user=emp, db=db)
            self.assertEqual(dash["unread_inbound"], 0)


if __name__ == "__main__":
    unittest.main()
