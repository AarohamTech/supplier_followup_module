"""Black chase targeting (client decision 2026-07-20): only still-pending
BLACK POs are chased — fully-received, cancel-requested and delisted ones are
dropped from the Black Follow-ups list."""
import os
import unittest
from contextlib import contextmanager
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_black_chase.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import ProcurementRecord  # noqa: E402
from app.services import ai_insights_service  # noqa: E402


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


def _black_line(db, po, supplier="ACME", **extra):
    db.add(ProcurementRecord(
        crm_no=f"C-{po}", supplier_po_no=po, material_name=f"M-{po}",
        supplier_name=supplier, signal="BLACK", **extra,
    ))
    db.commit()


class BlackChaseFilterTests(unittest.TestCase):
    def test_only_still_pending_blacks_are_chased(self):
        with _temp_db() as db:
            _black_line(db, "PO-PENDING")                                   # chase
            _black_line(db, "PO-RECEIVED", receipt_status="COMPLETED")      # skip
            _black_line(db, "PO-CANCELREQ", cancellation_status="PENDING")  # skip
            _black_line(db, "PO-DELISTED", delisted_at=datetime.utcnow())   # skip

            items = ai_insights_service.list_black_followups(db, limit=50)
            pos = {i["supplier_po_no"] for i in items}
            self.assertIn("PO-PENDING", pos)
            self.assertNotIn("PO-RECEIVED", pos)
            self.assertNotIn("PO-CANCELREQ", pos)

    def test_more_than_200_blacks_are_all_listed(self):
        # list_po_groups clamps size to 200 — the black list must page through,
        # not silently stop at the first 200 groups.
        with _temp_db() as db:
            for i in range(205):
                db.add(ProcurementRecord(
                    crm_no=f"C{i}", supplier_po_no=f"PO-{i:04d}", material_name=f"M{i}",
                    supplier_name="ACME", signal="BLACK",
                ))
            db.commit()
            items = ai_insights_service.list_black_followups(db, limit=300)
            self.assertEqual(len(items), 205)

    def test_mixed_po_with_one_pending_line_is_still_chased(self):
        with _temp_db() as db:
            _black_line(db, "PO-MIX", receipt_status="COMPLETED")
            db.add(ProcurementRecord(
                crm_no="C-MIX-2", supplier_po_no="PO-MIX", material_name="M-2",
                supplier_name="ACME", signal="BLACK",
            ))
            db.commit()
            items = ai_insights_service.list_black_followups(db, limit=50)
            self.assertIn("PO-MIX", {i["supplier_po_no"] for i in items})


if __name__ == "__main__":
    unittest.main()
