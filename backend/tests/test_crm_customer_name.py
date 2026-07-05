"""Fuzzy end-customer name extraction from a CRM desk row."""
import unittest

from app.services.crm_ingest_service import _customer_name


class CustomerNameTests(unittest.TestCase):
    def test_known_key(self):
        self.assertEqual(_customer_name({"CustomerName": "Tata Motors"}), "Tata Motors")

    def test_fuzzy_spaced_or_cased_key(self):
        self.assertEqual(_customer_name({"Customer Name": "Bajaj Auto"}), "Bajaj Auto")
        self.assertEqual(_customer_name({"customer_name": "Mahindra"}), "Mahindra")
        self.assertEqual(_customer_name({"PartyLongName": "L&T"}), "L&T")
        self.assertEqual(_customer_name({"BuyerName": "Ashok Leyland"}), "Ashok Leyland")

    def test_does_not_grab_po_code_or_date_fields(self):
        row = {
            "CustomerPoNo": "CPO-1",
            "CustomerGstNo": "27ABC",
            "CustomerPoDate": "2026-01-01",
            "CustomerCode": "C001",
        }
        self.assertIsNone(_customer_name(row))

    def test_does_not_grab_supplier_name(self):
        self.assertIsNone(_customer_name({"PoLongName": "ABC Supplier", "SupplierName": "ABC"}))

    def test_prefers_known_key_over_fuzzy(self):
        row = {"CustomerName": "Real Customer", "PartyDetails": "noise"}
        self.assertEqual(_customer_name(row), "Real Customer")


if __name__ == "__main__":
    unittest.main()
