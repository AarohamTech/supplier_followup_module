import unittest
from unittest.mock import patch

from app.services import communication_message_service as msg_service


class AutoMailQueueTests(unittest.TestCase):
    @patch("app.services.communication_message_service.create_message")
    def test_queue_outgoing_message_uses_ready_status_and_history_link(self, create_message) -> None:
        db = object()

        msg_service.queue_outgoing_message(
            db,
            supplier_id=7,
            supplier_name="Acme",
            procurement_record_id=11,
            supplier_po_no="PO-42",
            subject="Follow-up",
            body="Body",
            to_emails=["ops@example.com"],
            cc_emails=["buyer@example.com"],
            bcc_emails=["audit@example.com"],
            mail_type="YELLOW_REMINDER",
            mail_history_id=19,
            commit=False,
        )

        create_message.assert_called_once_with(
            db,
            direction="OUTGOING",
            status="READY",
            supplier_id=7,
            supplier_name="Acme",
            procurement_record_id=11,
            supplier_po_no="PO-42",
            customer_mail_id=None,
            subject="Follow-up",
            body="Body",
            body_html=None,
            sender_email=None,
            receiver_email="ops@example.com",
            to_emails=["ops@example.com"],
            cc_emails=["buyer@example.com"],
            bcc_emails=["audit@example.com"],
            mail_type="YELLOW_REMINDER",
            in_reply_to=None,
            raw_payload={"mail_history_id": 19},
            commit=False,
        )


if __name__ == "__main__":
    unittest.main()