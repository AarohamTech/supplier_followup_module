"""PO receipt quantities from the Hariom User Desk feed (PoQty/GrnQty/PendQty).

Covers the CRM field mapping (against the exact sample row from the Hariom mail),
the derived receipt status, the auto-follow-up skip for fully-received lines, and
the PO-level rollup in the grouped view.
"""
import unittest
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ProcurementRecord
from app.services import po_view_service as pv
from app.services.crm_ingest_service import _receipt_status, map_row
from app.services.po_followup_mail_service import _record_due_for_auto_mail
from app.services.procurement_sync_service import normalize_procurement_row

# The exact material line from the Hariom User Desk API mail (subset of fields).
MAIL_SAMPLE_ROW = {
    "TrnNo": "102192070111000164",
    "PoNo": "PO 000164",
    "TrnDate": "20190414",
    "PoType": "Open",
    "MaterialName": "BLIND SLEEVE 70 X 100 (55XP-M2.5X4)",
    "MaterialUom": "NOS",
    "Rate": 25.7,
    "PendQty": 1800.0,
    "PoValidity": "14/04/2019",
    "PoQty": 1800.0,
    "GrnQty": 1800.0,
}


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


class MappingTests(unittest.TestCase):
    def test_map_row_reads_mail_sample_fields(self):
        m = map_row(MAIL_SAMPLE_ROW)
        self.assertEqual(m["po_type"], "Open")
        self.assertEqual(m["po_qty"], 1800.0)
        self.assertEqual(m["grn_qty"], 1800.0)
        self.assertEqual(m["pending_qty"], 1800.0)

    def test_normalize_accepts_receipt_fields(self):
        norm, errs = normalize_procurement_row({
            "crm_no": "C1", "supplier_po_no": "PO1", "material_name": "M1",
            "po_type": "One Time", "po_qty": "100", "grn_qty": "40", "pending_qty": "60",
        })
        self.assertEqual(errs, [])
        self.assertEqual(norm["po_qty"], 100)
        self.assertEqual(norm["grn_qty"], 40)
        self.assertEqual(norm["pending_qty"], 60)
        self.assertEqual(norm["po_type"], "One Time")


class ReceiptStatusTests(unittest.TestCase):
    def test_open_po_is_ignored(self):
        # Open POs echo PoQty as PendQty (per Hariom IT) — quantities unreliable.
        self.assertIsNone(_receipt_status(map_row(MAIL_SAMPLE_ROW)))

    def test_completed_partial_pending(self):
        self.assertEqual(_receipt_status({"po_type": "One Time", "grn_qty": 100, "pending_qty": 0}), "COMPLETED")
        self.assertEqual(_receipt_status({"po_type": "One Time", "grn_qty": 40, "pending_qty": 60}), "PARTIAL")
        self.assertEqual(_receipt_status({"po_type": "One Time", "grn_qty": 0, "pending_qty": 100}), "PENDING")
        self.assertIsNone(_receipt_status({"po_type": None}))


class FollowupSkipTests(unittest.TestCase):
    def _rec(self, **kw):
        base = dict(mail_status="SENT", next_followup_date=None,
                    receipt_status=None, cancellation_status=None)
        base.update(kw)
        return type("R", (), base)()

    def test_completed_line_never_due(self):
        now = datetime.utcnow()
        self.assertTrue(_record_due_for_auto_mail(self._rec(), now))
        self.assertFalse(_record_due_for_auto_mail(self._rec(receipt_status="COMPLETED"), now))
        self.assertFalse(_record_due_for_auto_mail(self._rec(cancellation_status="PENDING"), now))
        self.assertFalse(_record_due_for_auto_mail(self._rec(cancellation_status="CANCELLED"), now))
        # Partial receipt still gets chased.
        self.assertTrue(_record_due_for_auto_mail(self._rec(receipt_status="PARTIAL"), now))


class GroupedRollupTests(unittest.TestCase):
    def _line(self, db, *, crm, po="PO1", receipt=None):
        db.add(ProcurementRecord(
            crm_no=crm, material_name=f"M-{crm}", supplier_po_no=po,
            supplier_name="Acme", receipt_status=receipt,
        ))
        db.commit()

    def _po1(self, db):
        items, _ = pv.grouped_pos(db)
        return [g for g in items if g["supplier_po_no"] == "PO1"][0]

    def test_all_lines_completed_rolls_up_completed(self):
        with _temp_db() as db:
            self._line(db, crm="C1", receipt="COMPLETED")
            self._line(db, crm="C2", receipt="COMPLETED")
            self.assertEqual(self._po1(db)["receipt_status"], "COMPLETED")

    def test_mixed_lines_roll_up_partial(self):
        with _temp_db() as db:
            self._line(db, crm="C1", receipt="COMPLETED")
            self._line(db, crm="C2", receipt="PENDING")
            self.assertEqual(self._po1(db)["receipt_status"], "PARTIAL")

    def test_untracked_lines_roll_up_none(self):
        with _temp_db() as db:
            self._line(db, crm="C1")
            self.assertIsNone(self._po1(db)["receipt_status"])

    def test_materials_detail_includes_quantities(self):
        with _temp_db() as db:
            db.add(ProcurementRecord(
                crm_no="C1", material_name="M1", supplier_po_no="PO1", supplier_name="Acme",
                po_qty=100, grn_qty=40, pending_qty=60, receipt_status="PARTIAL",
            ))
            db.commit()
            detail = pv.po_detail(db, supplier_po_no="PO1", supplier_name="Acme")
            m = detail["materials"][0]
            self.assertEqual((m["po_qty"], m["grn_qty"], m["pending_qty"]), (100.0, 40.0, 60.0))
            self.assertEqual(m["receipt_status"], "PARTIAL")


if __name__ == "__main__":
    unittest.main()
