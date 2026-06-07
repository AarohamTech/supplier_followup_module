"""Tests for the customer mail service helpers (DB-backed with SQLite memory)."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

# Force a throwaway SQLite DB for these tests so production data is not touched.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_customer_mail.sqlite")

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import CommunicationTask, CustomerMail  # noqa: E402,F401
from app.services import customer_mail_service  # noqa: E402


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class CustomerMailServiceTests(unittest.TestCase):
    def test_create_task_links_mail_to_task_and_updates_status(self) -> None:
        with _temp_db() as db:
            mail = CustomerMail(
                from_email="abc@buyer.com",
                from_name="ABC Buyer",
                subject="Order status",
                body="Where is my order",
                mail_type="CUSTOMER",
                status="OPEN",
                priority="P2",
            )
            db.add(mail)
            db.commit()
            db.refresh(mail)

            updated_mail, task = customer_mail_service.create_task_from_mail(
                db,
                mail.id,
                title="Reply to ABC",
                description=None,
                assigned_to="ops@example.com",
                priority="P1",
                due_date=None,
            )

            self.assertIsNotNone(updated_mail)
            self.assertIsNotNone(task)
            self.assertEqual(task.task_source, "CUSTOMER")
            self.assertEqual(task.customer_mail_id, mail.id)
            self.assertEqual(updated_mail.linked_task_id, task.id)
            self.assertEqual(updated_mail.status, "IN_PROGRESS")
            self.assertEqual(task.priority, "P1")
            self.assertEqual(task.assigned_to, "ops@example.com")

    def test_resolve_marks_status_and_stores_note(self) -> None:
        with _temp_db() as db:
            mail = CustomerMail(
                from_email="x@y.com",
                subject="Issue",
                body="Body",
                mail_type="GENERAL",
                status="OPEN",
                priority="P2",
            )
            db.add(mail)
            db.commit()
            db.refresh(mail)

            updated = customer_mail_service.resolve_mail(db, mail.id, resolution_note="done")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.status, "RESOLVED")
            self.assertIsNotNone(updated.raw_payload)
            self.assertEqual(updated.raw_payload.get("resolution_note"), "done")


if __name__ == "__main__":
    unittest.main()
