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

    def test_same_po_number_under_two_suppliers_is_judged_separately(self):
        # supplier_po_no is a recycled CRM counter, so identity is
        # (supplier, PO). One supplier's received line must not silence the
        # other supplier's still-pending line, or vice versa.
        with _temp_db() as db:
            # (crm_no, supplier_po_no, material_name) is unique, so the two
            # suppliers' lines carry their own material keys.
            db.add(ProcurementRecord(
                crm_no="C-ALPHA", supplier_po_no="PO-DUP", material_name="M-ALPHA",
                supplier_name="ALPHA", signal="BLACK",
            ))
            db.add(ProcurementRecord(
                crm_no="C-BETA", supplier_po_no="PO-DUP", material_name="M-BETA",
                supplier_name="BETA", signal="BLACK", receipt_status="COMPLETED",
            ))
            db.commit()
            items = ai_insights_service.list_black_followups(db, limit=50)
            suppliers = {i["supplier_name"] for i in items}
            self.assertIn("ALPHA", suppliers)
            self.assertNotIn("BETA", suppliers)

    def test_query_count_does_not_scale_with_po_count(self):
        # Regression guard: the page used to issue ~3 queries per group plus one
        # per group for the chase filter plus one per thread, and rebuilt every
        # group once per 200-row page. Against a cross-region DB that was 20s+.
        # Query count must stay flat as the number of black POs grows.
        from sqlalchemy import event

        def _count_for(n_pos: int) -> int:
            with _temp_db() as db:
                for i in range(n_pos):
                    db.add(ProcurementRecord(
                        crm_no=f"C{i}", supplier_po_no=f"PO-{i:04d}",
                        material_name=f"M{i}", supplier_name="ACME", signal="BLACK",
                    ))
                db.commit()
                engine = db.get_bind()
                seen = []
                def _on_exec(conn, cursor, statement, params, context, many):
                    seen.append(statement)
                event.listen(engine, "before_cursor_execute", _on_exec)
                try:
                    ai_insights_service.list_black_followups(db, limit=500)
                finally:
                    event.remove(engine, "before_cursor_execute", _on_exec)
                return len(seen)

        small = _count_for(5)
        large = _count_for(250)
        self.assertLessEqual(
            large, small + 2,
            f"query count grew with PO count ({small} -> {large}); the N+1 is back",
        )
        self.assertLessEqual(large, 12, f"expected a handful of queries, got {large}")


if __name__ == "__main__":
    unittest.main()
