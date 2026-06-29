"""Communication Hub unread-inbound surfacing + unread-first ordering.
DB-backed with in-memory SQLite (production data untouched)."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_hub_unread.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    ProcurementRecord,
    SupplierMaster,
)
from app.routers import communication_hub  # noqa: E402


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


def _supplier(db, name):
    s = SupplierMaster(supplier_name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _incoming(db, *, name, po, read=False):
    from datetime import datetime
    db.add(CommunicationMessage(
        direction="INCOMING", status="RECEIVED", channel="EMAIL",
        supplier_name=name, supplier_po_no=po, subject="reply", body="hi",
        read_at=datetime.utcnow() if read else None,
    ))
    db.commit()


class HubUnreadTests(unittest.TestCase):
    def test_unread_inbound_surfaced_and_sorted_first(self):
        with _temp_db() as db:
            _supplier(db, "ACME TOOLS")
            _supplier(db, "BETA PARTS")
            # ACME has an unread supplier reply; BETA's reply is already read.
            _incoming(db, name="ACME TOOLS", po="ACME-1", read=False)
            _incoming(db, name="BETA PARTS", po="BETA-1", read=True)

            rows = communication_hub.list_suppliers(db=db)
            by_name = {r["supplier_name"]: r for r in rows}
            self.assertEqual(by_name["ACME TOOLS"]["unread_inbound"], 1)
            self.assertEqual(by_name["BETA PARTS"]["unread_inbound"], 0)
            # Unread supplier must sort ahead of the read one.
            names = [r["supplier_name"] for r in rows]
            self.assertLess(names.index("ACME TOOLS"), names.index("BETA PARTS"))

    def test_opening_thread_clears_unread(self):
        with _temp_db() as db:
            _supplier(db, "ACME TOOLS")
            _incoming(db, name="ACME TOOLS", po="ACME-1", read=False)
            before = {r["supplier_name"]: r for r in communication_hub.list_suppliers(db=db)}
            self.assertEqual(before["ACME TOOLS"]["unread_inbound"], 1)

            # Mark the thread read (what opening a PO thread does).
            communication_hub.mark_thread_read(
                supplier_po_no="ACME-1", db=db)
            after = {r["supplier_name"]: r for r in communication_hub.list_suppliers(db=db)}
            self.assertEqual(after["ACME TOOLS"]["unread_inbound"], 0)


if __name__ == "__main__":
    unittest.main()
