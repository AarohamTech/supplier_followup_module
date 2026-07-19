"""Quantity sync from the Hariom pending-PO-list API (getpendingpolist).

Per the Hariom IT thread (Ninad's 2026-07-11 Postman screenshot), the PUBLIC
host serves `/api/procurement/getpendingpolist/{CompanyId}` with per-material
receipt quantities (PoQty/GrnQty/PendQty) plus TrnNo — the join key we already
store as `procurement_records.po_trn_no` (the desk feed's PoRefTrnNo). The sync
joins those quantities onto existing records and derives receipt_status.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_qty_sync.sqlite")

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ProcurementRecord
from app.services import crm_ingest_service as ingest
from app.services.crm_config import CrmConfig

CFG = CrmConfig(
    base_url="http://crm.example:8599", desk_id="102",
    login_email="x@y.z", login_password="pw", device_id="102",
)

# Field names as seen in the Postman screenshot of getpendingpolist/102.
QTY_ROW = {
    "TrnNo": "102262770111002342",
    "PoNo": "PO 002342",
    "PoType": "One Time",
    "MaterialName": "DUAL SPEED PENDANT FOR CHAIN HOIST",
    "MaterialUom": "NOS",
    "PoQty": 24.0,
    "GrnQty": 22.0,
    "PendQty": 2.0,
    "SupplierName": "ACCELERON HOISTING SOLUTIONS PRIVATE LIMITED",
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


def _line(db, *, crm="C1", po="PO1", material="DUAL SPEED PENDANT FOR CHAIN HOIST",
          trn="102262770111002342"):
    rec = ProcurementRecord(
        crm_no=crm, supplier_po_no=po, material_name=material,
        supplier_name="Acme", signal="GREEN", po_trn_no=trn,
    )
    db.add(rec)
    db.commit()
    return rec


class QtySyncTests(unittest.TestCase):
    def test_matching_line_gets_quantities_and_status(self):
        with _temp_db() as db:
            rec = _line(db, material="Dual Speed Pendant for Chain Hoist")  # case-insensitive
            with patch.object(ingest, "fetch_qty_list", return_value=[QTY_ROW]):
                stats = ingest.sync_quantities(db, CFG)
            db.refresh(rec)
            self.assertEqual(float(rec.po_qty), 24.0)
            self.assertEqual(float(rec.grn_qty), 22.0)
            self.assertEqual(float(rec.pending_qty), 2.0)
            self.assertEqual(rec.po_type, "One Time")
            self.assertEqual(rec.receipt_status, "PARTIAL")
            self.assertEqual(stats["matched"], 1)
            self.assertEqual(stats["updated"], 1)

    def test_pending_zero_completes_the_line(self):
        with _temp_db() as db:
            rec = _line(db)
            row = dict(QTY_ROW, GrnQty=24.0, PendQty=0.0)
            with patch.object(ingest, "fetch_qty_list", return_value=[row]):
                ingest.sync_quantities(db, CFG)
            db.refresh(rec)
            self.assertEqual(rec.receipt_status, "COMPLETED")

    def test_open_po_type_gets_no_receipt_status(self):
        with _temp_db() as db:
            rec = _line(db)
            row = dict(QTY_ROW, PoType="Open")
            with patch.object(ingest, "fetch_qty_list", return_value=[row]):
                ingest.sync_quantities(db, CFG)
            db.refresh(rec)
            self.assertIsNone(rec.receipt_status)
            self.assertEqual(float(rec.po_qty), 24.0)  # quantities still stored

    def test_unmatched_records_are_untouched(self):
        with _temp_db() as db:
            other = _line(db, crm="C2", trn="999999999999999999", material="SOMETHING ELSE")
            with patch.object(ingest, "fetch_qty_list", return_value=[QTY_ROW]):
                stats = ingest.sync_quantities(db, CFG)
            db.refresh(other)
            self.assertIsNone(other.po_qty)
            self.assertIsNone(other.receipt_status)
            self.assertEqual(stats["matched"], 0)

    def test_second_run_without_changes_updates_nothing(self):
        with _temp_db() as db:
            _line(db)
            with patch.object(ingest, "fetch_qty_list", return_value=[QTY_ROW]):
                first = ingest.sync_quantities(db, CFG)
                second = ingest.sync_quantities(db, CFG)
            self.assertEqual(first["updated"], 1)
            self.assertEqual(second["updated"], 0)

    def test_fetch_failure_is_reported_not_raised(self):
        with _temp_db() as db:
            _line(db)
            with patch.object(ingest, "fetch_qty_list", side_effect=RuntimeError("boom")), \
                 patch.object(ingest.settings, "CRM_QTY_SYNC_ENABLED", True):
                out = ingest._qty_sync_for_run(db, CFG, force=True)
            self.assertIsNotNone(out)
            self.assertIn("error", out)

    def test_flag_off_skips_entirely(self):
        with _temp_db() as db:
            with patch.object(ingest.settings, "CRM_QTY_SYNC_ENABLED", False):
                self.assertIsNone(ingest._qty_sync_for_run(db, CFG, force=True))


if __name__ == "__main__":
    unittest.main()
