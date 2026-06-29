"""Supplier Inbox: domain-based routing + listing."""
from __future__ import annotations

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CommunicationMessage, CustomerMail  # noqa: F401
from app.models.communication_message import CommunicationMessage as CM
from app.services import supplier_inbox_service as svc
from app.workers import mail_fetch_worker


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


def _raw_email(sender: str, subject: str = "Dispatch update", body: str = "Shipping soon.") -> bytes:
    return (
        f"From: Supplier X <{sender}>\r\n"
        f"To: us@ourco.com\r\n"
        f"Subject: {subject}\r\n"
        f"Message-ID: <test-{sender}>\r\n"
        f"Date: Mon, 28 Jun 2026 10:00:00 +0000\r\n"
        f"\r\n"
        f"{body}\r\n"
    ).encode("utf-8")


class SupplierDomainRoutingTests(unittest.TestCase):
    def test_zanvargroup_sender_routes_to_supplier_inbox_not_customer(self) -> None:
        with _temp_db() as db:
            out = mail_fetch_worker._process_one(db, b"1", _raw_email("ops@zanvargroup.com"))
            self.assertFalse(out.get("skipped"))
            # No customer mail created.
            self.assertEqual(int(db.scalar(select(func.count(CustomerMail.id))) or 0), 0)
            # A supplier-inbox communication message exists.
            msg = db.scalar(select(CM).where(CM.is_supplier_inbox.is_(True)))
            self.assertIsNotNone(msg)
            self.assertEqual(msg.direction, "INCOMING")
            self.assertIn("zanvargroup.com", (msg.sender_email or ""))

    def test_unknown_sender_still_routes_to_customer(self) -> None:
        with _temp_db() as db:
            mail_fetch_worker._process_one(db, b"2", _raw_email("random@somecustomer.com"))
            self.assertEqual(int(db.scalar(select(func.count(CustomerMail.id))) or 0), 1)
            self.assertIsNone(db.scalar(select(CM).where(CM.is_supplier_inbox.is_(True))))


class SupplierInboxListTests(unittest.TestCase):
    def test_list_filters_to_supplier_inbox(self) -> None:
        with _temp_db() as db:
            db.add_all([
                CM(direction="INCOMING", status="RECEIVED", is_supplier_inbox=True,
                   supplier_name="Acme", sender_email="a@zanvargroup.com", subject="hi"),
                CM(direction="INCOMING", status="RECEIVED", is_supplier_inbox=None,
                   sender_email="b@randomdomain.com", subject="nope"),
                CM(direction="OUTGOING", status="SENT", is_supplier_inbox=True,
                   sender_email="c@zanvargroup.com", subject="outgoing"),
            ])
            db.commit()
            rows, total = svc.list_supplier_inbox(db)
            self.assertEqual(total, 1)
            self.assertEqual(rows[0].subject, "hi")

    def test_list_includes_historical_domain_mail_without_tag(self) -> None:
        with _temp_db() as db:
            db.add(CM(direction="INCOMING", status="RECEIVED", is_supplier_inbox=None,
                      sender_email="legacy@zanvargroup.com", subject="old"))
            db.commit()
            rows, total = svc.list_supplier_inbox(db)
            self.assertEqual(total, 1)
            self.assertEqual(rows[0].subject, "old")


if __name__ == "__main__":
    unittest.main()
