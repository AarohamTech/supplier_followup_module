"""GREEN acknowledgement mails attach the official PO PDF — and it must be the
PDF of THIS supplier's PO.

Regression (2026-10-17): the attach step looked the CRM transaction number up
by ``supplier_po_no`` alone. That counter (CRM PoNo) is recycled across
suppliers, so SHIVAM ENGINEERS' ack for 2627-016280 went out carrying Super
Service's PO 2627-016287 (both on counter 004984).
"""
import os
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_green_ack_pdf.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import ProcurementRecord  # noqa: E402
from app.services import po_followup_mail_service as service  # noqa: E402
from app.services.crm_config import CrmConfig  # noqa: E402

CFG = CrmConfig(
    base_url="http://crm.example:8599", desk_id="102",
    login_email="x@y.z", login_password="pw", device_id="102",
)
SHIVAM_TRN = "101262770111016280"
SUPER_TRN = "101262770111016287"


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


def _rec(**kw):
    return ProcurementRecord(supplier_po_no="004984", **kw)


class GreenAckPoPdfTests(unittest.TestCase):
    def _attach(self, db, group):
        with patch("app.services.attachment_service.storage_enabled", return_value=True), \
             patch("app.services.attachment_service.save_upload",
                   return_value=SimpleNamespace(id=1)), \
             patch("app.services.attachment_service.bind"), \
             patch("app.services.crm_config.get_current_crm_config", return_value=CFG), \
             patch("app.services.notification_service.safe"), \
             patch("app.services.crm_ingest_service.fetch_po_pdf",
                   return_value=(b"%PDF-fake", "application/pdf")) as fetch:
            service._attach_po_pdf_to_green_ack(db, SimpleNamespace(id=99), group)
        return fetch

    def test_pdf_is_the_groups_own_po_not_a_sibling_on_the_recycled_counter(self):
        with _temp_db() as db:
            # Another supplier's PO on the same recycled counter, inserted first.
            other = _rec(crm_no="C0", material_name="PROXI SWITCH", supplier_name="Super Service",
                         po_short_ref="2627-016287", po_trn_no=SUPER_TRN)
            mine = _rec(crm_no="C1", material_name="POWER CONTACTOR", supplier_name="SHIVAM ENGINEERS",
                        po_short_ref="2627-016280", po_trn_no=SHIVAM_TRN)
            db.add_all([other, mine])
            db.commit()

            fetch = self._attach(db, {
                "supplier_po_no": "004984", "supplier_name": "SHIVAM ENGINEERS",
                "po_ref": "2627-016280", "procurement_record_ids": [mine.id],
            })

        fetch.assert_called_once_with(CFG, SHIVAM_TRN)

    def test_without_record_ids_the_lookup_stays_scoped_to_the_supplier(self):
        with _temp_db() as db:
            db.add_all([
                _rec(crm_no="C0", material_name="X", supplier_name="Super Service", po_trn_no=SUPER_TRN),
                _rec(crm_no="C1", material_name="Y", supplier_name="SHIVAM ENGINEERS", po_trn_no=SHIVAM_TRN),
            ])
            db.commit()

            fetch = self._attach(db, {
                "supplier_po_no": "004984", "supplier_name": "Shivam Engineers",
                "procurement_record_ids": [],
            })

        fetch.assert_called_once_with(CFG, SHIVAM_TRN)

    def test_no_pdf_when_the_po_cannot_be_pinned_to_the_supplier(self):
        with _temp_db() as db:
            db.add(_rec(crm_no="C0", material_name="X", supplier_name="Super Service", po_trn_no=SUPER_TRN))
            db.commit()

            fetch = self._attach(db, {
                "supplier_po_no": "004984", "supplier_name": None, "procurement_record_ids": [],
            })

        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
