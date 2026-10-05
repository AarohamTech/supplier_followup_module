"""Configurable board columns, the task assigner ("Assigned by you") and task
attachment scoping. DB-backed with in-memory SQLite (production data untouched)."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_task_board.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import CommunicationTask, User  # noqa: E402,F401
from app.models.message_attachment import MessageAttachment  # noqa: E402
from app.routers import communication as comm  # noqa: E402
from app.routers import employee_portal  # noqa: E402
from app.schemas.communication_task import (  # noqa: E402
    CommunicationTaskCreate,
    CommunicationTaskUpdate,
)
from app.services import task_board_service as board  # noqa: E402
from app.services import user_service  # noqa: E402


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


def _keys(cols):
    return [c["key"] for c in cols]


class BoardColumnTests(unittest.TestCase):
    def test_defaults_are_the_seven_builtins(self):
        with _temp_db() as db:
            cols = board.get_columns(db)
        self.assertEqual(
            _keys(cols),
            ["BACKLOG", "TODO", "IN_PROGRESS", "WAITING_SUPPLIER", "WAITING_CUSTOMER", "BLOCKED", "DONE"],
        )
        self.assertTrue(all(c["builtin"] for c in cols))

    def test_custom_column_gets_a_minted_key_and_is_a_valid_status(self):
        with _temp_db() as db:
            cols = board.set_columns(db, board.get_columns(db) + [{"label": "QC Pending", "color": "teal"}])
            self.assertIn("C_QC_PENDING", _keys(cols))
            self.assertIn("C_QC_PENDING", board.valid_status_keys(db))

    def test_builtins_cannot_be_dropped_and_done_cannot_be_hidden(self):
        with _temp_db() as db:
            cols = board.set_columns(db, [{"key": "DONE", "label": "Closed", "hidden": True}])
        self.assertEqual(len(cols), 7, "every built-in survives a payload that omits it")
        done = next(c for c in cols if c["key"] == "DONE")
        self.assertEqual(done["label"], "Closed")
        self.assertFalse(done["hidden"])
        self.assertEqual(cols[0]["key"], "DONE", "the stored order is kept")

    def test_removing_a_custom_column_moves_its_tasks_to_todo(self):
        with _temp_db() as db:
            board.set_columns(db, board.get_columns(db) + [{"label": "QC Pending"}])
            db.add(CommunicationTask(title="t", status="C_QC_PENDING", watchers=[]))
            db.commit()
            board.set_columns(db, [c for c in board.get_columns(db) if c["key"] != "C_QC_PENDING"])
            task = db.query(CommunicationTask).one()
            db.refresh(task)
        self.assertEqual(task.status, "TODO")

    def test_task_can_move_into_a_custom_column_but_not_an_unknown_one(self):
        with _temp_db() as db:
            admin = user_service.create_user(db, email="a@corp.com", password="x" * 8, role=Role.ADMIN)
            board.set_columns(db, board.get_columns(db) + [{"label": "Payment"}])
            task = comm.create_task(payload=CommunicationTaskCreate(title="pay"), db=db, actor=admin)
            moved = comm.update_task(
                task_id=task.id, payload=CommunicationTaskUpdate(status="C_PAYMENT"), db=db, actor=admin)
            self.assertEqual(moved.status, "C_PAYMENT")
            with self.assertRaises(HTTPException) as ctx:
                comm.update_task(
                    task_id=task.id, payload=CommunicationTaskUpdate(status="C_NOPE"), db=db, actor=admin)
            self.assertEqual(ctx.exception.status_code, 422)


class AssignerTests(unittest.TestCase):
    def test_creator_is_recorded_and_reassigning_changes_the_assigner(self):
        with _temp_db() as db:
            alice = user_service.create_user(db, email="alice@corp.com", password="x" * 8, role=Role.USER)
            bob = user_service.create_user(db, email="bob@corp.com", password="x" * 8, role=Role.USER)
            carol = user_service.create_user(db, email="carol@corp.com", password="x" * 8, role=Role.USER)

            task = comm.create_task(
                payload=CommunicationTaskCreate(title="x", assigned_to_user_id=bob.id), db=db, actor=alice)
            self.assertEqual(task.assigned_by_user_id, alice.id)

            # A non-assignment edit keeps the original assigner.
            comm.update_task(task_id=task.id, payload=CommunicationTaskUpdate(priority="HIGH"), db=db, actor=bob)
            self.assertEqual(task.assigned_by_user_id, alice.id)

            comm.update_task(
                task_id=task.id, payload=CommunicationTaskUpdate(assigned_to_user_id=carol.id), db=db, actor=bob)
            self.assertEqual(task.assigned_by_user_id, bob.id)

    def test_employee_sees_tasks_they_assigned_to_someone_else(self):
        with _temp_db() as db:
            emp = user_service.create_user(
                db, email="emp@corp.com", password="x" * 8, role=Role.USER, emp_code="E1")
            other = user_service.create_user(db, email="o@corp.com", password="x" * 8, role=Role.USER)
            task = employee_portal.create_task(
                payload=CommunicationTaskCreate(title="for other", assigned_to_user_id=other.id),
                user=emp, db=db)
            ids = [t.id for t in employee_portal.my_tasks(user=emp, db=db)]
        self.assertIn(task.id, ids)


class TaskAttachmentScopeTests(unittest.TestCase):
    def test_employee_can_download_a_file_on_a_task_in_scope_only(self):
        from unittest.mock import patch

        with _temp_db() as db:
            emp = user_service.create_user(
                db, email="emp@corp.com", password="x" * 8, role=Role.USER, emp_code="E1")
            mine = CommunicationTask(title="mine", assigned_to_user_id=emp.id, watchers=[])
            theirs = CommunicationTask(title="theirs", watchers=[])
            db.add_all([mine, theirs])
            db.commit()
            ok = MessageAttachment(filename="a.pdf", storage_key="k1", uploaded_by_kind="staff",
                                   uploaded_by_id=99, task_id=mine.id)
            nope = MessageAttachment(filename="b.pdf", storage_key="k2", uploaded_by_kind="staff",
                                     uploaded_by_id=99, task_id=theirs.id)
            db.add_all([ok, nope])
            db.commit()

            with patch("app.routers.attachments.attachment_response", return_value="FILE"):
                self.assertEqual(
                    employee_portal.download_attachment(attachment_id=ok.id, user=emp, db=db), "FILE")
                with self.assertRaises(HTTPException):
                    employee_portal.download_attachment(attachment_id=nope.id, user=emp, db=db)

    def test_only_uploader_or_admin_can_remove_a_task_file(self):
        from unittest.mock import patch

        with _temp_db() as db:
            up = user_service.create_user(db, email="up@corp.com", password="x" * 8, role=Role.USER)
            other = user_service.create_user(db, email="ot@corp.com", password="x" * 8, role=Role.USER)
            admin = user_service.create_user(db, email="ad@corp.com", password="x" * 8, role=Role.ADMIN)
            task = CommunicationTask(title="t", watchers=[], attachment_count=2)
            db.add(task)
            db.commit()
            a1 = MessageAttachment(filename="1", storage_key="k1", uploaded_by_kind="staff",
                                   uploaded_by_id=up.id, task_id=task.id)
            a2 = MessageAttachment(filename="2", storage_key="k2", uploaded_by_kind="staff",
                                   uploaded_by_id=up.id, task_id=task.id)
            db.add_all([a1, a2])
            db.commit()

            with patch("app.services.attachment_service._client"):
                with self.assertRaises(HTTPException) as ctx:
                    comm.remove_task_attachment(db, task, a1.id, other)
                self.assertEqual(ctx.exception.status_code, 403)
                comm.remove_task_attachment(db, task, a1.id, up)
                comm.remove_task_attachment(db, task, a2.id, admin)
            self.assertEqual(db.query(MessageAttachment).count(), 0)
            self.assertEqual(task.attachment_count, 0)


if __name__ == "__main__":
    unittest.main()
