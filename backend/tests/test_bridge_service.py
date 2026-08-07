"""The ZanFlow bridge — task upsert, assignee resolution, and the callback out.

ZanFlow (the material-enquiry system) pushes a task here whenever it assigns a
material line, keyed on `(external_system, external_ref)`. The key is enforced
in application code rather than as a unique constraint, because
`core/schema_evolve.py` only ever ADDs columns to the live schema — the same
reason `users.username` uniqueness lives in app code. So the idempotency test
below is not decoration: it is the only thing holding that key.

DB-backed with in-memory SQLite (production data untouched).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_bridge.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import CommunicationTask, User  # noqa: E402
from app.models.task_collaboration import TaskComment  # noqa: E402,F401
from app.services import bridge_service as svc  # noqa: E402


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


def _user(db, *, email, name, emp_code=None, supplier_id=None, active=True) -> User:
    row = User(
        email=email,
        full_name=name,
        hashed_password="x",
        role="employee" if emp_code else "user",
        is_active=active,
        emp_code=emp_code,
        supplier_id=supplier_id,
    )
    db.add(row)
    db.flush()
    return row


def _payload(**over) -> dict:
    base = {
        "external_system": "zanflow",
        "external_ref": "MR-1042-M2",
        "external_url": "https://zflow.example/materials/MR-1042-M2",
        "title": "MR-1042-M2 · Bearing 6205 ZZ",
        "description": "SKF, sealed both sides.",
        "material_name": "Bearing 6205 ZZ",
        "priority": "HIGH",
        "status": "IN_PROGRESS",
        "due_date": datetime(2026, 8, 20),
        "assignee": None,
        "assigned_by": "Ninad Pawar",
    }
    base.update(over)
    return base


class UpsertTests(unittest.TestCase):
    def test_first_call_creates_an_internal_task_carrying_its_external_key(self):
        with _temp_db() as db:
            task, created, unmapped = svc.upsert_external_task(db, **_payload())

            self.assertTrue(created)
            self.assertFalse(unmapped)
            self.assertEqual(task.external_system, "zanflow")
            self.assertEqual(task.external_ref, "MR-1042-M2")
            self.assertEqual(task.external_url, "https://zflow.example/materials/MR-1042-M2")
            self.assertEqual(task.task_source, "INTERNAL")
            self.assertEqual(task.priority, "HIGH")
            self.assertEqual(task.status, "IN_PROGRESS")
            self.assertEqual(task.material_name, "Bearing 6205 ZZ")
            self.assertEqual(task.assigned_by, "Ninad Pawar")

    def test_second_call_on_the_same_ref_updates_rather_than_duplicating(self):
        with _temp_db() as db:
            first, _, _ = svc.upsert_external_task(db, **_payload())
            second, created, _ = svc.upsert_external_task(
                db, **_payload(title="MR-1042-M2 · Bearing 6205 2RS", priority="LOW")
            )

            self.assertFalse(created)
            self.assertEqual(first.id, second.id)
            self.assertEqual(db.query(CommunicationTask).count(), 1)
            self.assertEqual(second.title, "MR-1042-M2 · Bearing 6205 2RS")
            self.assertEqual(second.priority, "LOW")

    def test_a_different_ref_is_a_different_task(self):
        with _temp_db() as db:
            svc.upsert_external_task(db, **_payload(external_ref="MR-1042-M2"))
            svc.upsert_external_task(db, **_payload(external_ref="MR-1042-M3"))
            self.assertEqual(db.query(CommunicationTask).count(), 2)

    def test_status_is_seeded_on_create_but_never_overwritten_on_update(self):
        """ZanFlow's stage seeds the first status. After that the portal owns it —
        otherwise every edit here would be stamped back to the stage's default."""
        with _temp_db() as db:
            task, _, _ = svc.upsert_external_task(db, **_payload(status="TODO"))
            task.status = "WAITING_SUPPLIER"
            db.flush()

            again, _, _ = svc.upsert_external_task(db, **_payload(status="TODO"))
            self.assertEqual(again.status, "WAITING_SUPPLIER")


class AssigneeResolutionTests(unittest.TestCase):
    def test_explicit_followup_user_id_wins(self):
        with _temp_db() as db:
            u = _user(db, email="pramod@zanvargroup.com", name="Pramod Kale", emp_code="PRAMOD")
            task, _, unmapped = svc.upsert_external_task(
                db, **_payload(assignee={"followup_user_id": u.id, "email": None,
                                         "display_name": "whatever"})
            )
            self.assertFalse(unmapped)
            self.assertEqual(task.assigned_to_user_id, u.id)
            self.assertEqual(task.assigned_to, "Pramod Kale")
            self.assertIsNotNone(task.assigned_at)

    def test_email_match_is_case_insensitive(self):
        with _temp_db() as db:
            u = _user(db, email="pramod@zanvargroup.com", name="Pramod Kale", emp_code="PRAMOD")
            task, _, unmapped = svc.upsert_external_task(
                db, **_payload(assignee={"followup_user_id": None,
                                         "email": "PRAMOD@ZanvarGroup.com",
                                         "display_name": "Pramod K"})
            )
            self.assertFalse(unmapped)
            self.assertEqual(task.assigned_to_user_id, u.id)

    def test_no_counterpart_leaves_the_task_on_the_staff_board_and_says_so(self):
        """The task must still exist — an unmappable assignee is not a failure,
        it is a task nobody has claimed yet."""
        with _temp_db() as db:
            task, created, unmapped = svc.upsert_external_task(
                db, **_payload(assignee={"followup_user_id": None, "email": None,
                                         "display_name": "Shop Floor Store"})
            )
            self.assertTrue(created)
            self.assertTrue(unmapped)
            self.assertIsNone(task.assigned_to_user_id)
            self.assertEqual(task.assigned_to, "Shop Floor Store")

    def test_a_supplier_account_is_never_an_assignee(self):
        """Suppliers are outside the staff ladder; `list_assignees` excludes them
        and so must this door, or ZanFlow could hand a supplier internal work."""
        with _temp_db() as db:
            s = _user(db, email="vendor@acme.com", name="Acme", supplier_id=1)
            task, _, unmapped = svc.upsert_external_task(
                db, **_payload(assignee={"followup_user_id": s.id, "email": None,
                                         "display_name": "Acme"})
            )
            self.assertTrue(unmapped)
            self.assertIsNone(task.assigned_to_user_id)

    def test_a_deactivated_account_is_not_an_assignee(self):
        with _temp_db() as db:
            u = _user(db, email="gone@zanvargroup.com", name="Gone", active=False)
            _, _, unmapped = svc.upsert_external_task(
                db, **_payload(assignee={"followup_user_id": u.id, "email": None,
                                         "display_name": "Gone"})
            )
            self.assertTrue(unmapped)

    def test_a_stale_followup_user_id_falls_back_to_the_email(self):
        """ZanFlow caches the id. If the account is rebuilt, the cache is wrong —
        the email still finds the right person rather than dropping the task."""
        with _temp_db() as db:
            u = _user(db, email="pramod@zanvargroup.com", name="Pramod Kale")
            task, _, unmapped = svc.upsert_external_task(
                db, **_payload(assignee={"followup_user_id": 9999,
                                         "email": "pramod@zanvargroup.com",
                                         "display_name": "Pramod Kale"})
            )
            self.assertFalse(unmapped)
            self.assertEqual(task.assigned_to_user_id, u.id)


class CallbackOutTests(unittest.TestCase):
    def test_a_task_with_no_external_system_never_calls_out(self):
        with _temp_db() as db:
            row = CommunicationTask(title="ordinary task")
            db.add(row)
            db.flush()
            with patch.object(svc.requests, "post") as post:
                svc.notify_zanflow(db, row, event="STATUS_CHANGED", status="DONE")
            post.assert_not_called()

    def test_a_bridged_task_posts_the_callback_with_the_secret(self):
        with _temp_db() as db:
            task, _, _ = svc.upsert_external_task(db, **_payload())
            with patch.object(svc.settings, "ZANFLOW_API_BASE", "https://zf.example"), \
                 patch.object(svc.settings, "ZANFLOW_CALLBACK_SECRET", "s3cret"), \
                 patch.object(svc.requests, "post") as post:
                post.return_value = MagicMock(status_code=200)
                svc.notify_zanflow(db, task, event="STATUS_CHANGED",
                                   status="WAITING_SUPPLIER", progress_percent=40,
                                   actor="Pramod Kale")

            post.assert_called_once()
            url = post.call_args.args[0]
            body = post.call_args.kwargs["json"]
            headers = post.call_args.kwargs["headers"]
            self.assertEqual(
                url, "https://zf.example/api/v1/zanflow/integrations/followup/callback"
            )
            self.assertEqual(headers["X-Bridge-Secret"], "s3cret")
            self.assertEqual(body["external_ref"], "MR-1042-M2")
            self.assertEqual(body["event"], "STATUS_CHANGED")
            self.assertEqual(body["status"], "WAITING_SUPPLIER")
            self.assertEqual(body["progress_percent"], 40)
            self.assertEqual(body["actor"], "Pramod Kale")

    def test_an_unreachable_zanflow_does_not_raise(self):
        """A portal user changing a status must not be shown an error because a
        different system is down."""
        with _temp_db() as db:
            task, _, _ = svc.upsert_external_task(db, **_payload())
            with patch.object(svc.settings, "ZANFLOW_API_BASE", "https://zf.example"), \
                 patch.object(svc.settings, "ZANFLOW_CALLBACK_SECRET", "s3cret"), \
                 patch.object(svc.requests, "post", side_effect=OSError("connection refused")):
                svc.notify_zanflow(db, task, event="STATUS_CHANGED", status="DONE")
            # no assertion beyond "did not raise"

    def test_no_base_url_configured_is_a_silent_no_op(self):
        with _temp_db() as db:
            task, _, _ = svc.upsert_external_task(db, **_payload())
            with patch.object(svc.settings, "ZANFLOW_API_BASE", ""), \
                 patch.object(svc.requests, "post") as post:
                svc.notify_zanflow(db, task, event="STATUS_CHANGED", status="DONE")
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
