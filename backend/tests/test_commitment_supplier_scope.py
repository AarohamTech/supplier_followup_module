"""Feature 4 — commitment identity is (supplier_name, supplier_po_no, material_name).

CRM PoNo is recycled across suppliers, so two suppliers sharing a PO number and a
material name must get two independent commitment rows, and a lookup scoped by
supplier must return only that supplier's row.

DB-backed with in-memory SQLite (production data untouched).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import date

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_commitment_scope.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import SupplierMaterialCommitment  # noqa: E402,F401
from app.services import po_followup_service as svc  # noqa: E402


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


PO = "000449"
MATERIAL = "PS SC DRILL DIA 6"


def _commit(db, supplier_name: str, remark: str) -> SupplierMaterialCommitment:
    return svc.upsert_commitment(
        db,
        supplier_po_no=PO,
        material_name=MATERIAL,
        procurement_record_id=None,
        supplier_id=None,
        supplier_name=supplier_name,
        material_code=None,
        commitment_qty=1,
        commitment_date_value=date(2026, 7, 15),
        supplier_status="CONFIRMED",
        supplier_remark=remark,
        reply_mail_id=None,
        commit=True,
    )


class CommitmentSupplierScopeTests(unittest.TestCase):
    def test_shared_po_and_material_creates_two_rows(self):
        with _temp_db() as db:
            _commit(db, "Vedant Tools Pvt Ltd", "vedant remark")
            _commit(db, "ALFA TOOLINGS", "alfa remark")

            rows = db.query(SupplierMaterialCommitment).all()
            self.assertEqual(len(rows), 2)
            by_supplier = {r.supplier_name: r.supplier_remark for r in rows}
            self.assertEqual(by_supplier["Vedant Tools Pvt Ltd"], "vedant remark")
            self.assertEqual(by_supplier["ALFA TOOLINGS"], "alfa remark")

    def test_second_reply_from_same_supplier_updates_in_place(self):
        with _temp_db() as db:
            _commit(db, "Vedant Tools Pvt Ltd", "first")
            _commit(db, "Vedant Tools Pvt Ltd", "second")
            rows = db.query(SupplierMaterialCommitment).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].supplier_remark, "second")

    def test_list_commitments_scoped_by_supplier(self):
        with _temp_db() as db:
            _commit(db, "Vedant Tools Pvt Ltd", "vedant remark")
            _commit(db, "ALFA TOOLINGS", "alfa remark")

            alfa = svc.list_commitments(db, supplier_po_no=PO, supplier_name="alfa toolings")
            self.assertEqual(len(alfa), 1)
            self.assertEqual(alfa[0]["supplier_remark"], "alfa remark")

            both = svc.list_commitments(db, supplier_po_no=PO)
            self.assertEqual(len(both), 2)

    def test_load_commitments_scoped_by_supplier(self):
        with _temp_db() as db:
            _commit(db, "Vedant Tools Pvt Ltd", "vedant remark")
            _commit(db, "ALFA TOOLINGS", "alfa remark")

            loaded = svc._load_commitments(db, PO, "Vedant Tools Pvt Ltd")
            self.assertEqual(len(loaded), 1)
            only = next(iter(loaded.values()))
            self.assertEqual(only.supplier_name, "Vedant Tools Pvt Ltd")


if __name__ == "__main__":
    unittest.main()
