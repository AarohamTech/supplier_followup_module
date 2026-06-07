import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import po_followup_mail_service as service


class PoFollowupMailServiceTests(unittest.TestCase):
    def test_queue_due_po_followups_respects_feature_flag(self) -> None:
        with patch.object(service.settings, "AUTO_PO_FOLLOWUP_ENABLED", False):
            result = service.queue_due_po_followups(MagicMock())

        self.assertFalse(result["enabled"])
        self.assertEqual(result["queued"], 0)

    @patch("app.services.po_followup_mail_service.po_followup_service.get_po_group")
    def test_create_po_followup_mail_skips_missing_mapping_when_required(self, get_group) -> None:
        get_group.return_value = {
            "supplier_name": "Acme",
            "supplier_po_no": "PO-42",
            "overall_signal": "YELLOW",
            "material_count": 1,
            "mapping_active": False,
        }

        result = service.create_po_followup_mail(
            MagicMock(),
            supplier_name="Acme",
            supplier_po_no="PO-42",
            require_mapping=True,
        )

        self.assertFalse(result.created)
        self.assertEqual(result.skipped_reason, "No active supplier email mapping")
        self.assertEqual(result.mail_type, "PO_FOLLOWUP_YELLOW")

    @patch("app.services.po_followup_mail_service.find_active_po_mail")
    @patch("app.services.po_followup_mail_service.po_followup_service.build_po_group_payload")
    @patch("app.services.po_followup_mail_service.apply_followup_logic")
    def test_queue_due_po_followups_dry_run_reports_due_group(
        self,
        apply_followup_logic,
        build_group,
        find_active,
    ) -> None:
        rec = SimpleNamespace(
            supplier_name="Acme",
            supplier_po_no="PO-42",
            mail_status="NOT_SENT",
            next_followup_date=datetime.utcnow() - timedelta(minutes=1),
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = [rec]
        build_group.return_value = {
            "supplier_name": "Acme",
            "supplier_po_no": "PO-42",
            "overall_signal": "RED",
            "material_count": 2,
            "mapping_active": True,
        }
        find_active.return_value = None

        with patch.object(service.settings, "AUTO_PO_FOLLOWUP_ENABLED", True):
            result = service.queue_due_po_followups(db, dry_run=True)

        self.assertTrue(result["enabled"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["queued"], 1)
        self.assertEqual(result["results"][0]["mail_type"], "PO_FOLLOWUP_RED")
        apply_followup_logic.assert_called_once_with(rec, db=db)
        db.rollback.assert_called_once_with()

    @patch("app.services.po_followup_mail_service.find_active_po_mail")
    @patch("app.services.po_followup_mail_service.po_followup_service.build_po_group_payload")
    @patch("app.services.po_followup_mail_service.apply_followup_logic")
    def test_queue_due_po_followups_skips_missing_mapping_in_dry_run(
        self,
        apply_followup_logic,
        build_group,
        find_active,
    ) -> None:
        rec = SimpleNamespace(
            supplier_name="Acme",
            supplier_po_no="PO-42",
            mail_status="NOT_SENT",
            next_followup_date=None,
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = [rec]
        build_group.return_value = {
            "supplier_name": "Acme",
            "supplier_po_no": "PO-42",
            "overall_signal": "YELLOW",
            "material_count": 1,
            "mapping_active": False,
        }

        with patch.object(service.settings, "AUTO_PO_FOLLOWUP_ENABLED", True):
            result = service.queue_due_po_followups(db, dry_run=True)

        self.assertEqual(result["queued"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["results"][0]["skipped_reason"], "No active supplier email mapping")
        find_active.assert_not_called()


if __name__ == "__main__":
    unittest.main()
