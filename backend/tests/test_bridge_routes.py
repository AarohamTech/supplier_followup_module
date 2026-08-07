"""The /api/bridge door, and the two places a bridged task calls back out.

The secret tests matter more than they look: `/api/bridge/*` is mounted next to
`auth` and `webhooks` on the open side of `main.py`, outside every RBAC guard,
because its caller is a machine with no session. The only thing between it and
the internet is `require_webhook_secret` — so a test that it is actually
attached, and actually fails closed when no secret is configured, is the test
that the door is a door.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_bridge_routes.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import CommunicationTask, User  # noqa: E402
from app.routers import bridge as bridge_router  # noqa: E402
from app.routers import communication as comm  # noqa: E402
from app.routers.webhooks import require_webhook_secret  # noqa: E402
from app.schemas.bridge import BridgeAssignee, BridgeTaskIn  # noqa: E402
from app.schemas.communication_task import CommunicationTaskUpdate  # noqa: E402
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


def _staff(db) -> User:
    row = User(email="ninad@zanvargroup.com", full_name="Ninad Pawar",
               hashed_password="x", role="admin", is_active=True)
    db.add(row)
    db.flush()
    return row


def _task_in(**over) -> BridgeTaskIn:
    base = dict(
        external_system="zanflow",
        external_ref="MR-1042-M2",
        title="MR-1042-M2 · Bearing 6205 ZZ",
        external_url="https://zflow.example/materials/MR-1042-M2",
        priority="HIGH",
        status="IN_PROGRESS",
        assigned_by="Ninad Pawar",
    )
    base.update(over)
    return BridgeTaskIn(**base)


class SecretTests(unittest.TestCase):
    def test_the_router_carries_the_shared_secret_dependency(self):
        deps = [d.dependency for d in bridge_router.router.dependencies]
        self.assertIn(require_webhook_secret, deps)

    def test_no_secret_configured_rejects_every_call(self):
        with patch("app.routers.webhooks.settings") as s:
            s.WEBHOOK_SECRET = None
            with self.assertRaises(HTTPException) as caught:
                require_webhook_secret(x_webhook_secret="anything")
        self.assertEqual(caught.exception.status_code, 503)

    def test_a_wrong_secret_is_401(self):
        with patch("app.routers.webhooks.settings") as s:
            s.WEBHOOK_SECRET = "right"
            with self.assertRaises(HTTPException) as caught:
                require_webhook_secret(x_webhook_secret="wrong")
        self.assertEqual(caught.exception.status_code, 401)


class UpsertRouteTests(unittest.TestCase):
    def test_creating_reports_created_and_logs_the_activity(self):
        with _temp_db() as db:
            out = bridge_router.upsert_bridge_task(_task_in(), db=db)
            self.assertTrue(out.created)
            self.assertEqual(out.status, "IN_PROGRESS")
            types = [a.activity_type for a in db.query(
                __import__("app.models.task_collaboration", fromlist=["x"]).TaskActivityLog
            ).all()]
            self.assertIn("CREATED", types)

    def test_pushing_the_same_ref_twice_reports_created_false_and_keeps_one_row(self):
        with _temp_db() as db:
            bridge_router.upsert_bridge_task(_task_in(), db=db)
            out = bridge_router.upsert_bridge_task(_task_in(title="renamed"), db=db)
            self.assertFalse(out.created)
            self.assertEqual(db.query(CommunicationTask).count(), 1)

    def test_an_unmapped_assignee_is_reported_not_refused(self):
        with _temp_db() as db:
            out = bridge_router.upsert_bridge_task(
                _task_in(assignee=BridgeAssignee(display_name="Shop Floor Store")), db=db
            )
            self.assertTrue(out.unmapped_assignee)
            self.assertIsNone(out.assigned_to_user_id)
            self.assertEqual(out.assigned_to, "Shop Floor Store")
            self.assertEqual(db.query(CommunicationTask).count(), 1)

    def test_read_back_reports_current_state(self):
        with _temp_db() as db:
            bridge_router.upsert_bridge_task(_task_in(), db=db)
            out = bridge_router.read_bridge_task("MR-1042-M2", db=db)
            self.assertTrue(out["found"])
            self.assertEqual(out["status"], "IN_PROGRESS")

    def test_read_back_of_an_unknown_ref_is_found_false_not_an_error(self):
        with _temp_db() as db:
            self.assertEqual(bridge_router.read_bridge_task("nope", db=db), {"found": False})

    def test_task_source_cannot_be_set_by_the_caller(self):
        """INTERNAL is imposed. An external system does not get to label its
        work as an escalation to jump the board's filters."""
        with _temp_db() as db:
            bridge_router.upsert_bridge_task(_task_in(), db=db)
            row = db.query(CommunicationTask).one()
            self.assertEqual(row.task_source, "INTERNAL")
        self.assertNotIn("task_source", BridgeTaskIn.model_fields)


class CallbackHookTests(unittest.TestCase):
    """Status changes and comments must reach ZanFlow from every surface."""

    def test_a_status_change_notifies(self):
        with _temp_db() as db:
            actor = _staff(db)
            bridge_router.upsert_bridge_task(_task_in(), db=db)
            task = db.query(CommunicationTask).one()

            with patch.object(comm.bridge, "safe_notify") as notify:
                comm.update_task(
                    task_id=task.id,
                    payload=CommunicationTaskUpdate(status="WAITING_SUPPLIER"),
                    db=db, actor=actor,
                )
            notify.assert_called_once()
            self.assertEqual(notify.call_args.kwargs["event"], "STATUS_CHANGED")
            self.assertEqual(notify.call_args.kwargs["status"], "WAITING_SUPPLIER")

    def test_an_edit_that_changes_no_status_does_not_notify(self):
        with _temp_db() as db:
            actor = _staff(db)
            bridge_router.upsert_bridge_task(_task_in(), db=db)
            task = db.query(CommunicationTask).one()

            with patch.object(comm.bridge, "safe_notify") as notify:
                comm.update_task(
                    task_id=task.id,
                    payload=CommunicationTaskUpdate(title="just a rename"),
                    db=db, actor=actor,
                )
            notify.assert_not_called()

    def test_a_comment_notifies_with_its_text(self):
        with _temp_db() as db:
            actor = _staff(db)
            bridge_router.upsert_bridge_task(_task_in(), db=db)
            task = db.query(CommunicationTask).one()

            with patch.object(comm.bridge, "safe_notify") as notify:
                comm.add_task_comment(
                    task_id=task.id,
                    body={"comment": "Quote chased, supplier says Tuesday."},
                    db=db, actor=actor,
                )
            notify.assert_called_once()
            self.assertEqual(notify.call_args.kwargs["event"], "COMMENT_ADDED")
            self.assertEqual(
                notify.call_args.kwargs["comment"], "Quote chased, supplier says Tuesday."
            )
            self.assertEqual(notify.call_args.kwargs["actor"], "Ninad Pawar")

    def test_an_ordinary_task_notifies_nobody(self):
        """The hook fires for every task; `notify_zanflow` is what filters. Prove
        the filter holds, or every PO task would POST to ZanFlow."""
        with _temp_db() as db:
            actor = _staff(db)
            row = CommunicationTask(title="chase Acme", status="TODO")
            db.add(row)
            db.commit()

            with patch.object(svc.settings, "ZANFLOW_API_BASE", "https://zf.example"), \
                 patch.object(svc.settings, "ZANFLOW_CALLBACK_SECRET", "s3cret"), \
                 patch.object(svc.requests, "post") as post:
                post.return_value = MagicMock(status_code=200)
                comm.update_task(
                    task_id=row.id,
                    payload=CommunicationTaskUpdate(status="DONE"),
                    db=db, actor=actor,
                )
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
