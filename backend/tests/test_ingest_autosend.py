"""Change 6: freshly-ingested POs are immediately due so the green/yellow/red
follow-up fires on arrival (instead of waiting 24h)."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_ingest.sqlite")

from app.models import ProcurementRecord  # noqa: E402
from app.services import crm_ingest_service  # noqa: E402
from app.services.po_followup_mail_service import _record_due_for_auto_mail  # noqa: E402


class IngestAutoSendTests(unittest.TestCase):
    def test_new_record_next_followup_is_now_not_24h(self):
        vals = crm_ingest_service._col_values(
            {"crm_no": "C1", "material_name": "M", "supplier_po_no": "PO-1", "signal": "GREEN"}
        )
        now = datetime.utcnow()
        # Due immediately (allow a small clock delta), never 24h out.
        self.assertLessEqual(vals["next_followup_date"], now + timedelta(seconds=2))
        self.assertEqual(vals["mail_status"], "NOT_SENT")

    def test_fresh_record_is_due_for_auto_mail(self):
        now = datetime.utcnow()
        rec = ProcurementRecord(
            crm_no="C1", material_name="M", supplier_po_no="PO-1",
            signal="GREEN", mail_status="NOT_SENT", next_followup_date=now,
        )
        self.assertTrue(_record_due_for_auto_mail(rec, now))


if __name__ == "__main__":
    unittest.main()
