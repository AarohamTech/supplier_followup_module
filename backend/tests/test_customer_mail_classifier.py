"""Tests for the customer mail classifier."""
import unittest

from app.workers.mail_fetch_worker import _classify_customer_mail


class CustomerMailClassifierTests(unittest.TestCase):
    def test_classifies_dispatch_keywords(self) -> None:
        self.assertEqual(
            _classify_customer_mail("Shipment notice", "Your order has been shipped"),
            "DISPATCH",
        )

    def test_classifies_quality_keywords(self) -> None:
        self.assertEqual(
            _classify_customer_mail("Quality issue", "We rejected the batch"),
            "QUALITY",
        )

    def test_classifies_complaint_keywords(self) -> None:
        self.assertEqual(
            _classify_customer_mail("Complaint about service", "There is an issue"),
            "COMPLAINT",
        )

    def test_classifies_customer_keywords(self) -> None:
        self.assertEqual(
            _classify_customer_mail("RFQ for new material", "Please send quotation"),
            "CUSTOMER",
        )

    def test_falls_back_to_general(self) -> None:
        self.assertEqual(_classify_customer_mail("Hello", "Just saying hi"), "GENERAL")


if __name__ == "__main__":
    unittest.main()
