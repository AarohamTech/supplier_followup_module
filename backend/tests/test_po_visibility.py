"""Suppliers must never see or be mailed about NOT APPROVED / NOT GENERATED POs.

The CRM desk feed now lands every status in procurement_records so staff and
employees can chase approvals internally. Every supplier-facing surface filters
through ``po_visibility``; these tests pin the predicate and its three callers
(supplier portal scope, portal AI tool ownership, auto follow-up queue).
"""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ProcurementRecord
from app.routers import portal
from app.services import ai_tools_service, po_followup_mail_service as pfm, po_visibility as vis


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


def _line(db, *, crm, po, status, supplier="ACME TOOLS", signal="RED"):
    r = ProcurementRecord(
        crm_no=crm, material_name=f"M-{crm}", supplier_po_no=po, supplier_name=supplier,
        po_status=status, signal=signal, owner_emp_code="E1",
    )
    db.add(r)
    db.commit()
    return r


class PredicateTests(unittest.TestCase):
    def test_only_the_not_states_are_hidden(self):
        self.assertTrue(vis.is_awaiting_approval("NOT APPROVED"))
        self.assertTrue(vis.is_awaiting_approval(" not generated "))
        for ok in ("APPROVED", None, "", "CONFIRMED", "DISPATCHED", "OPEN"):
            self.assertFalse(vis.is_awaiting_approval(ok), ok)

    def test_sql_clause_matches_python_predicate(self):
        with _temp_db() as db:
            for i, st in enumerate(["APPROVED", "NOT APPROVED", "NOT GENERATED", None, "CONFIRMED"]):
                _line(db, crm=f"C{i}", po=f"PO{i}", status=st)
            from sqlalchemy import select
            visible = {r.po_status for r in db.scalars(
                select(ProcurementRecord).where(vis.supplier_visible_clause())
            ).all()}
            self.assertEqual(visible, {"APPROVED", None, "CONFIRMED"})


class SupplierPortalScopeTests(unittest.TestCase):
    def test_portal_po_records_skip_unapproved_lines(self):
        with _temp_db() as db:
            _line(db, crm="C1", po="PO1", status="APPROVED")
            _line(db, crm="C2", po="PO2", status="NOT APPROVED")
            _line(db, crm="C3", po="PO3", status="NOT GENERATED")
            pos = {r.supplier_po_no for r in portal._po_records(db, "ACME TOOLS")}
            self.assertEqual(pos, {"PO1"})
            self.assertIsNone(portal._po_is_owned(db, "ACME TOOLS", "PO2"))
            self.assertIsNotNone(portal._po_is_owned(db, "ACME TOOLS", "PO1"))

    def test_portal_ai_tools_do_not_own_unapproved_pos(self):
        with _temp_db() as db:
            _line(db, crm="C1", po="PO1", status="APPROVED")
            _line(db, crm="C2", po="PO2", status="NOT APPROVED")
            scope = ai_tools_service.ToolScope(supplier_id=1, supplier_name="ACME TOOLS")
            self.assertTrue(ai_tools_service._owns_po(db, scope, "PO1"))
            self.assertFalse(ai_tools_service._owns_po(db, scope, "PO2"))


class FollowupQueueTests(unittest.TestCase):
    def test_auto_queue_never_considers_unapproved_pos(self):
        with _temp_db() as db:
            _line(db, crm="C1", po="PO1", status="NOT APPROVED")
            _line(db, crm="C2", po="PO2", status="NOT GENERATED", supplier=None)
            with patch.object(pfm.settings, "AUTO_PO_FOLLOWUP_ENABLED", True, create=True):
                out = pfm.queue_due_po_followups(db, dry_run=True)
            self.assertEqual(out["queued"], 0)
            # Nothing was even evaluated: no per-PO result rows at all.
            self.assertEqual(out["results"], [])

    def test_manual_send_for_unapproved_po_is_skipped_with_reason(self):
        with _temp_db() as db:
            _line(db, crm="C1", po="PO1", status="NOT APPROVED")
            res = pfm.create_po_followup_mail(
                db, supplier_name="ACME TOOLS", supplier_po_no="PO1", commit=True,
            )
            self.assertFalse(res.created)
            self.assertEqual(res.skipped_reason, pfm.NOT_APPROVED_SKIP)


if __name__ == "__main__":
    unittest.main()
