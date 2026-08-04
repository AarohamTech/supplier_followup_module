"""Internal senders must never be attributed to a supplier.

Supplier email mappings legitimately contain the buyer's OWN staff addresses
(cc so staff stay in the loop, escalation so managers get escalations). The
sender-identity lookup matched the sender against ALL arrays, so an internal
forward from sandeep@hariomtech.in — listed in Vedant Tools' escalation list —
was ingested as a "Vedant Tools reply" and showed in their hub thread.
Bounce daemons (mailer-deamon@...) were attributed the same way via the PO
body-scan and piled up as fake supplier replies (65 in prod).

Rule: a sender on the company's own mail domain, or any bounce daemon, is
never a supplier. Their mails route to the Customer Mails inbox instead.

Uses the in-memory SQLite pattern: call functions directly, prod untouched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_mail_attribution.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import SupplierEmail, SupplierMaster  # noqa: E402,F401
from app.services import communication_message_service as msg_service  # noqa: E402


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


def _mapping(db, *, name="Vedant Tools Pvt Ltd", to=None, cc=None, esc=None):
    sup = SupplierMaster(supplier_name=name)
    db.add(sup)
    db.commit()
    db.refresh(sup)
    row = SupplierEmail(
        supplier_id=sup.id,
        supplier_name=name,
        to_emails=to or [],
        cc_emails=cc or [],
        bcc_emails=[],
        escalation_emails=esc or [],
        is_active=True,
    )
    db.add(row)
    db.commit()
    return sup


def _with_internal_domain(domain="hariomtech.in"):
    return mock.patch.object(
        msg_service.settings, "IMAP_USER", f"stores@{domain}", create=True
    )


class InternalSenderTests(unittest.TestCase):
    def test_is_internal_sender_company_domain(self):
        with _with_internal_domain():
            self.assertTrue(msg_service.is_internal_sender("sandeep@hariomtech.in"))
            self.assertFalse(msg_service.is_internal_sender("sales@vedanttools.com"))

    def test_is_internal_sender_bounce_daemons(self):
        with _with_internal_domain():
            for addr in (
                "mailer-deamon@hariomtech.in",   # the exact prod misspelling
                "mailer-daemon@some-relay.com",
                "MAILER-DAEMON@googlemail.com",
                "postmaster@vedanttools.com",
                "no-reply@notifier.example.com",
            ):
                self.assertTrue(msg_service.is_internal_sender(addr), addr)

    def test_staff_in_escalation_list_is_not_the_supplier(self):
        with _temp_db() as db, _with_internal_domain():
            _mapping(
                db,
                to=["sales@vedanttools.com"],
                cc=["ninad@hariomtech.in"],
                esc=["sandeep@hariomtech.in"],
            )
            self.assertEqual(
                msg_service.find_supplier_by_email(db, "sandeep@hariomtech.in"),
                (None, None),
            )
            self.assertEqual(
                msg_service.find_supplier_by_email(db, "ninad@hariomtech.in"),
                (None, None),
            )

    def test_real_supplier_address_still_matches(self):
        with _temp_db() as db, _with_internal_domain():
            sup = _mapping(
                db,
                to=["sales@vedanttools.com"],
                cc=["satish.patil@vedanttools.com"],
                esc=["sandeep@hariomtech.in"],
            )
            self.assertEqual(
                msg_service.find_supplier_by_email(db, "sales@vedanttools.com"),
                (sup.id, "Vedant Tools Pvt Ltd"),
            )
            # cc entries that are genuinely the supplier's people still match.
            self.assertEqual(
                msg_service.find_supplier_by_email(db, "satish.patil@vedanttools.com"),
                (sup.id, "Vedant Tools Pvt Ltd"),
            )


if __name__ == "__main__":
    unittest.main()
