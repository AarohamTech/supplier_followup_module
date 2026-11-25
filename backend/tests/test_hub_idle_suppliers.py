"""Hub supplier list hides suppliers whose POs are all closed/expired and have
nothing unread; the signal comes from open lines only. In-memory SQLite."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_hub_idle.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import CommunicationMessage, ProcurementRecord  # noqa: E402,F401
from app.models.mail_history import MailHistory  # noqa: E402
from app.models.supplier import SupplierMaster  # noqa: E402
from app.routers import communication_hub as hub  # noqa: E402


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _rec(db, name, po, *, closed=False, signal="GREEN"):
    db.add(ProcurementRecord(
        crm_no=f"C-{name}-{po}", material_name="Bolt", supplier_po_no=po, supplier_name=name,
        signal=signal, delisted_at=datetime(2026, 11, 1) if closed else None,
    ))


class IdleSupplierTests(unittest.TestCase):
    def test_idle_hidden_unread_kept_signal_from_open_lines(self):
        with _temp_db() as db:
            for n in ("LIVE", "EXPIRED", "UNREAD"):
                db.add(SupplierMaster(supplier_name=n, is_active=True))
            _rec(db, "LIVE", "001", signal="GREEN")
            _rec(db, "EXPIRED", "002", closed=True, signal="BLACK")
            _rec(db, "UNREAD", "003", closed=True)
            # An old BLACK chase mail must not paint LIVE black.
            db.add(MailHistory(procurement_record_id=1, supplier_name="LIVE", supplier_po_no="009",
                               material_name="x", subject="s", body="b",
                               mail_type="PO_FOLLOWUP_BLACK", sent_status="SENT"))
            db.add(CommunicationMessage(direction="INCOMING", status="RECEIVED",
                                        supplier_name="UNREAD", supplier_po_no="003",
                                        subject="Re", body="dispatched"))
            db.commit()

            rows = {s["supplier_name"]: s for s in hub.list_suppliers(db=db)}
            self.assertEqual(set(rows), {"LIVE", "UNREAD"})
            self.assertEqual(rows["LIVE"]["highest_signal"], "GREEN")
            self.assertEqual(rows["LIVE"]["mail_count"], 1)

            everyone = {s["supplier_name"] for s in hub.list_suppliers(db=db, include_idle=True)}
            self.assertEqual(everyone, {"LIVE", "EXPIRED", "UNREAD"})


if __name__ == "__main__":
    unittest.main()
