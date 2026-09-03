"""CRM ingest keeps every PO status (APPROVED / NOT APPROVED / NOT GENERATED) and
stores the raw desk row, so staff can see unapproved POs and the ERP cancel
request can carry every original field."""
import unittest

from app.services import crm_ingest_service as svc

APPROVED = {"CRMNo": "C1", "PoNo": "000449", "MaterialName": "SLEEVE", "PoStatus": "APPROVED",
            "PoLongName": "VEDANT", "Extra": "x"}
NOT_APPROVED = {"CRMNo": "C2", "PoNo": "000450", "MaterialName": "PLATE", "PoStatus": "NOT APPROVED",
                "PoLongName": "VEDANT"}
NOT_GENERATED = {"CRMNo": "C3", "PoNo": "000451", "MaterialName": "ROD", "PoStatus": "NOT GENERATED",
                 "PoLongName": None}
NO_KEY = {"CRMNo": "C4", "PoNo": "", "MaterialName": "BAR", "PoStatus": "NOT GENERATED"}


class IngestFilterTests(unittest.TestCase):
    def test_every_status_with_a_business_key_is_ingestible(self):
        self.assertTrue(svc._ingestible(APPROVED))
        self.assertTrue(svc._ingestible(NOT_APPROVED))
        self.assertTrue(svc._ingestible(NOT_GENERATED), "no vendor yet is fine")
        self.assertFalse(svc._ingestible(NO_KEY), "no PoNo -> cannot be keyed")

    def test_generated_still_means_approved_with_vendor(self):
        self.assertTrue(svc._is_generated(APPROVED))
        self.assertFalse(svc._is_generated(NOT_APPROVED))
        self.assertFalse(svc._is_generated(NOT_GENERATED))

    def test_map_row_keeps_the_whole_feed_row(self):
        mapped = svc.map_row(APPROVED)
        self.assertEqual(mapped["po_status"], "APPROVED")
        self.assertEqual(mapped["crm_raw"], APPROVED)
        self.assertIsNot(mapped["crm_raw"], APPROVED, "a copy, not the feed object")
        cols = svc._col_values({**mapped, "qty": None, "quantity": None})
        self.assertEqual(cols["crm_raw"]["Extra"], "x")
        self.assertEqual(cols["po_status"], "APPROVED")

    def test_raw_row_does_not_change_the_content_hash(self):
        a = svc._source_hash({**svc.map_row(APPROVED)})
        b = svc._source_hash({**svc.map_row({**APPROVED, "Extra": "changed"})})
        self.assertEqual(a, b, "unmapped feed noise must not rewrite every row each poll")


if __name__ == "__main__":
    unittest.main()
