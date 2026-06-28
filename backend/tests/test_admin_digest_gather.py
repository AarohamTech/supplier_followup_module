import unittest
from datetime import datetime
from types import SimpleNamespace

from app.services import admin_digest_service as svc

TODAY = datetime(2026, 6, 27)


def rec(**kw):
    base = dict(supplier_po_no="PO-1", supplier_name="Acme", material_name="Bolt",
                signal="RED", escalation_level="LEVEL_1", risk_score=70,
                risk_band="HIGH", risk_reason="overdue", shipment_date=datetime(2026, 6, 20),
                followup_status="URGENT_FOLLOWUP")
    base.update(kw)
    return SimpleNamespace(**base)


class GatherFormatTests(unittest.TestCase):
    def test_days_late_positive_and_none(self):
        self.assertEqual(svc._days_late(datetime(2026, 6, 20), TODAY), 7)
        self.assertIsNone(svc._days_late(None, TODAY))
        self.assertEqual(svc._days_late(datetime(2026, 6, 30), TODAY), 0)  # future -> 0, not negative

    def test_format_critical_shapes_and_orders_fields(self):
        rows = [rec(supplier_po_no="PO-9", signal="BLACK", risk_score=96,
                    shipment_date=datetime(2026, 6, 8))]
        out = svc.format_critical(rows, TODAY)
        self.assertEqual(out[0]["po"], "PO-9")
        self.assertEqual(out[0]["signal"], "Black")     # title-cased label
        self.assertEqual(out[0]["days_late"], 19)
        self.assertEqual(out[0]["risk"], 96)

    def test_format_overdue_labels_due_today_vs_overdue(self):
        rows = [rec(supplier_po_no="A", shipment_date=datetime(2026, 6, 27)),
                rec(supplier_po_no="B", shipment_date=datetime(2026, 6, 20))]
        out = svc.format_overdue(rows, TODAY)
        self.assertEqual(out[0]["status"], "Due today")
        self.assertEqual(out[1]["status"], "Overdue")

    def test_summarize_counts_builds_signal_map(self):
        active = [rec(signal="GREEN"), rec(signal="GREEN"), rec(signal="BLACK"), rec(signal=None)]
        counts = svc.summarize_counts(active, overdue_count=3, critical_count=1, new_replies=5)
        self.assertEqual(counts["active"], 4)
        self.assertEqual(counts["signals"]["GREEN"], 2)
        self.assertEqual(counts["signals"]["BLACK"], 1)
        self.assertEqual(counts["overdue"], 3)
        self.assertEqual(counts["new_replies"], 5)
