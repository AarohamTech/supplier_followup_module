"""One vendor PO (po_short_ref) spread over two recycled CRM counters gets ONE
follow-up mail, not one per counter (25-Nov: 2627-019982 = 012736 + 012738).
In-memory SQLite."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ProcurementRecord
from app.models.mail_history import MailHistory
from app.models.supplier import SupplierMaster
from app.models.supplier_email import SupplierEmail
from app.services import po_followup_mail_service as pfm


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


def _line(db, crm, counter, ref, material):
    db.add(ProcurementRecord(
        crm_no=crm, material_name=material, supplier_po_no=counter, po_short_ref=ref,
        supplier_name="SHIVAM ENGINEERS", po_status="APPROVED", signal="GREEN", qty=10,
    ))


class OneMailPerVendorPoTests(unittest.TestCase):
    def test_two_counters_same_vendor_po_one_mail(self):
        with _temp_db() as db:
            sup = SupplierMaster(supplier_name="SHIVAM ENGINEERS", is_active=True)
            db.add(sup)
            db.flush()
            db.add(SupplierEmail(supplier_id=sup.id, supplier_name=sup.supplier_name,
                                 to_emails=["s@shivam.test"], is_active=True))
            _line(db, "2627-021830", "012738", "2627-019982", "3M PLATE")
            _line(db, "2627-021830", "012738", "2627-019982", "SURFACE BOX PVC 3 MODULE")
            _line(db, "2627-021831", "012736", "2627-019982", "MCB 6A TP")
            db.commit()

            with patch.object(pfm.settings, "AUTO_PO_FOLLOWUP_ENABLED", True, create=True), \
                 patch.object(pfm, "_send_realtime_now", return_value=0), \
                 patch.object(pfm, "_attach_po_pdf_to_green_ack"):
                out = pfm.queue_due_po_followups(db)
                again = pfm.queue_due_po_followups(db)

            mails = db.scalars(select(MailHistory)).all()
            self.assertEqual(len(mails), 1, [m.subject for m in mails])
            self.assertIn("2627-019982", mails[0].subject)
            self.assertIn("3 material", mails[0].subject)
            self.assertEqual(out["queued"], 1)
            self.assertEqual(again["queued"], 0)


if __name__ == "__main__":
    unittest.main()
