"""Feature 3a — CRM ingest maps end-customer fields and stops copying po_no.

po_no must hold the CUSTOMER PO (distinct from the recycled CRM PoNo /
supplier_po_no); customer_name and po_date must be populated from the feed.
"""
from __future__ import annotations

import os
import unittest
from datetime import date

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_ingest_customer.sqlite")

from app.schemas.procurement import ProcurementCreate  # noqa: E402
from app.services import crm_ingest_service as crm  # noqa: E402
from app.services.procurement_sync_service import normalize_procurement_row  # noqa: E402


def _col_values_for(raw_crm_row: dict) -> dict:
    mapped = crm.map_row(raw_crm_row)
    norm, errs = normalize_procurement_row(mapped)
    assert not errs, errs
    payload = ProcurementCreate(**norm).model_dump()
    return crm._col_values(payload)


BASE_ROW = {
    "CRMNo": "2627-001507",
    "PoNo": "000449",
    "MaterialName": "SC NTC STEP BURNISHING DRILL",
    "PoLongName": "Vedant Tools Pvt Ltd",
    "PoStatus": "APPROVED",
    "Signal": "RED",
}


class IngestCustomerFieldTests(unittest.TestCase):
    def test_customer_fields_mapped(self):
        row = {
            **BASE_ROW,
            "CustomerName": "ZANVAR GROUP",
            "CustomerPoNo": "ZG-9001",
            "CustomerPoDate": "21-05-2026",
        }
        cv = _col_values_for(row)
        self.assertEqual(cv["customer_name"], "ZANVAR GROUP")
        self.assertEqual(cv["po_no"], "ZG-9001")  # customer PO, not supplier PO
        self.assertEqual(cv["po_date"], date(2026, 5, 21))
        self.assertEqual(cv["supplier_po_no"], "000449")

    def test_po_no_falls_back_to_supplier_po_when_no_customer_po(self):
        cv = _col_values_for(dict(BASE_ROW))
        self.assertEqual(cv["po_no"], "000449")  # fallback preserves not-null
        self.assertIsNone(cv["customer_name"])
        self.assertIsNone(cv["po_date"])

    def test_customer_fields_participate_in_source_hash(self):
        base = crm.map_row(dict(BASE_ROW))
        withcust = crm.map_row({**BASE_ROW, "CustomerName": "ZANVAR GROUP"})
        self.assertNotEqual(crm._source_hash(base), crm._source_hash(withcust))


if __name__ == "__main__":
    unittest.main()
