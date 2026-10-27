"""Employee password reset: the temp password is always returned for the admin
to hand out, and is ALSO emailed when the employee has a real email address
(placeholder @employee.local addresses have no mailbox)."""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_employee_reset.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.services import employee_account_service as svc  # noqa: E402
from app.services import supplier_account_service, user_service  # noqa: E402


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


def _employee(db, email):
    return user_service.create_user(
        db, email=email, password="old", role="employee",
        emp_code="0000000001", username="chinmay", full_name="chinmay pisal",
    )


class EmployeeResetEmailTests(unittest.TestCase):
    def test_real_email_gets_the_temp_password_mailed(self):
        with _temp_db() as db:
            user = _employee(db, "chinmaypisal45@gmail.com")
            with patch.object(supplier_account_service, "send_credentials_email",
                              return_value=True) as send:
                out = svc.reset_employee_password(db, user)

        self.assertTrue(out["emailed"])
        self.assertEqual(out["email"], "chinmaypisal45@gmail.com")
        kw = send.call_args.kwargs
        self.assertEqual(kw["email"], "chinmaypisal45@gmail.com")
        self.assertEqual(kw["temp_password"], out["temp_password"])
        self.assertEqual(kw["login_id"], "chinmay")
        self.assertEqual(kw["audience"], "employee")
        self.assertTrue(kw["is_reset"])

    def test_placeholder_email_is_not_mailed(self):
        with _temp_db() as db:
            user = _employee(db, "chinmay.0000000001@employee.local")
            with patch.object(supplier_account_service, "send_credentials_email") as send:
                out = svc.reset_employee_password(db, user)

        send.assert_not_called()
        self.assertFalse(out["emailed"])
        self.assertIsNone(out["email"])
        self.assertTrue(out["temp_password"])

    def test_employee_mail_text_names_the_username_not_the_supplier_portal(self):
        with _temp_db() as db, \
             patch("app.services.communication_message_service.queue_outgoing_message") as queue, \
             patch("app.workers.mail_send_worker.send_message_now", return_value={"sent": True}):
            queue.return_value.id = 1
            supplier_account_service.send_credentials_email(
                db, email="e@x.com", temp_password="T3mp", supplier_name="chinmay pisal",
                is_reset=True, audience="employee", login_id="chinmay",
            )
        kw = queue.call_args.kwargs
        self.assertIn("chinmay", kw["body"])
        self.assertIn("T3mp", kw["body"])
        self.assertNotIn("Supplier", kw["subject"])
        self.assertEqual(kw["mail_type"], "EMPLOYEE_PORTAL_CREDENTIALS")


if __name__ == "__main__":
    unittest.main()
