"""Supplier portal: messages carry the rendered email (body_html), and
"Open in Outlook" is addressed to the company inbox with the PO ref."""
import os
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_portal_outlook.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import CommunicationMessage, ProcurementRecord, SupplierMaster  # noqa: E402
from app.routers import portal  # noqa: E402
from app.services import user_service  # noqa: E402


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


def _seed(db):
    sup = SupplierMaster(supplier_name="ACME", is_active=True)
    db.add(sup)
    db.commit()
    user = user_service.create_user(db, email="s@acme.com", password="pw", role="supplier", supplier_id=sup.id)
    db.add(ProcurementRecord(
        crm_no="C1", supplier_po_no="004984", material_name="Drill", supplier_name="ACME",
        po_short_ref="2627-016280", po_status="APPROVED",
    ))
    db.commit()
    return sup, user


class PortalOutlookTests(unittest.TestCase):
    def test_outlook_compose_goes_to_the_company_inbox_with_the_po_ref(self):
        with _temp_db() as db:
            _, user = _seed(db)
            with patch("app.services.mail_config_service.get_imap_config",
                       return_value=SimpleNamespace(user="stores@hariomtech.in")):
                out = portal.po_outlook_compose("004984", user=user, db=db)
        self.assertEqual(out.to, ["stores@hariomtech.in"])
        self.assertIn("2627-016280", out.subject)

    def test_outlook_falls_back_to_the_sending_mailbox(self):
        with _temp_db() as db:
            _, user = _seed(db)
            with patch("app.services.mail_config_service.get_imap_config",
                       return_value=SimpleNamespace(user="")), \
                 patch("app.services.mail_config_service.get_smtp_config",
                       return_value=SimpleNamespace(from_addr="sales@hariomtech.in")):
                out = portal.po_outlook_compose("004984", user=user, db=db)
        self.assertEqual(out.to, ["sales@hariomtech.in"])

    def test_outlook_is_refused_for_a_po_that_is_not_the_suppliers(self):
        with _temp_db() as db:
            _, user = _seed(db)
            with self.assertRaises(HTTPException) as ctx:
                portal.po_outlook_compose("999999", user=user, db=db)
        self.assertEqual(ctx.exception.status_code, 404)


class PortalMessageHtmlTests(unittest.TestCase):
    def test_follow_up_mail_is_returned_with_its_html(self):
        with _temp_db() as db:
            sup, user = _seed(db)
            db.add(CommunicationMessage(
                direction="OUTGOING", status="SENT", supplier_id=sup.id, supplier_name="ACME",
                supplier_po_no="004984", subject="PO Follow-up", body="Dear ACME",
                body_html="<table><tr><td>Material-wise summary</td></tr></table>",
                mail_type="PO_FOLLOWUP_GREEN",
            ))
            db.add(CommunicationMessage(
                direction="INCOMING", status="RECEIVED", supplier_id=sup.id, supplier_name="ACME",
                supplier_po_no="004984", subject="Re", body="Will ship Friday", mail_type="PORTAL_MESSAGE",
            ))
            db.commit()
            rows = portal.list_po_messages("004984", user=user, db=db)

        by_type = {r.mail_type: r for r in rows}
        self.assertIn("Material-wise summary", by_type["PO_FOLLOWUP_GREEN"].body_html)
        self.assertEqual(by_type["PO_FOLLOWUP_GREEN"].body, "Dear ACME")
        self.assertIsNone(by_type["PORTAL_MESSAGE"].body_html)


if __name__ == "__main__":
    unittest.main()
