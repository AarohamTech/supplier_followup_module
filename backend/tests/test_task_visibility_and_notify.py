"""Task visibility, task notifications, "My tasks" export and source-mail
context (client feedback 2026-11). In-memory SQLite; production data untouched."""
from __future__ import annotations

import io
import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_task_visibility.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    Notification,
    ProcurementRecord,
    User,
)
from app.models.message_attachment import MessageAttachment  # noqa: E402
from app.routers import communication as comm  # noqa: E402
from app.routers import communication_hub as hub  # noqa: E402
from app.routers import employee_portal  # noqa: E402
from app.schemas.communication_task import (  # noqa: E402
    CommunicationTaskCreate,
    CommunicationTaskUpdate,
)
from app.services import notification_service, task_visibility, user_service  # noqa: E402


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


def _user(db, name, role=Role.USER, emp_code=None):
    return user_service.create_user(
        db, email=f"{name}@corp.com", password="x" * 8, role=role,
        emp_code=emp_code, username=name if emp_code else None, full_name=name.title(),
    )


def _task(db, title, **kw):
    kw.setdefault("status", "TODO")
    kw.setdefault("watchers", [])
    t = CommunicationTask(title=title, **kw)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _notes(db, user):
    return notification_service.list_for_user(db, user.id, limit=100)


class VisibilityTests(unittest.TestCase):
    def test_non_admin_sees_only_involved_open_tasks_admin_sees_all(self):
        with _temp_db() as db:
            admin = _user(db, "admin", Role.ADMIN)
            alice = _user(db, "alice", Role.MANAGER)
            bob = _user(db, "bob")
            _task(db, "assigned", assigned_to_user_id=alice.id)
            _task(db, "created", created_by_user_id=alice.id)
            _task(db, "assigner", assigned_by_user_id=alice.id, assigned_to_user_id=bob.id)
            _task(db, "watching", watchers=[alice.id])
            _task(db, "done-mine", status="DONE", assigned_to_user_id=alice.id)
            _task(db, "bobs", assigned_to_user_id=bob.id)
            _task(db, "orphan")

            mine = {t.title for t in comm.tasks_index(db=db, overdue=False, limit=500, viewer=alice)}
            self.assertEqual(mine, {"assigned", "created", "assigner", "watching"})
            self.assertEqual({t.title for t in comm.list_tasks(db=db, limit=500, viewer=alice)}, mine)

            everything = {t.title for t in comm.tasks_index(db=db, overdue=False, limit=500, viewer=admin)}
            self.assertEqual(len(everything), 7)
            self.assertIn("done-mine", everything)

    def test_watcher_like_prefilter_has_no_false_positives(self):
        with _temp_db() as db:
            users = [_user(db, f"u{i}") for i in range(16)]
            u1 = users[0]
            # A watcher id that contains u1's id as a substring must not match.
            other_id = next(u.id for u in users if str(u1.id) in str(u.id) and u.id != u1.id)
            _task(db, "not mine", watchers=[other_id])
            self.assertEqual(comm.tasks_index(db=db, overdue=False, limit=500, viewer=u1), [])

    def test_get_update_delete_404_when_not_involved(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            bob = _user(db, "bob")
            t = _task(db, "bobs", assigned_to_user_id=bob.id)
            with self.assertRaises(HTTPException) as cm:
                comm.get_task(task_id=t.id, db=db, viewer=alice)
            self.assertEqual(cm.exception.status_code, 404)
            with self.assertRaises(HTTPException):
                comm.update_task(task_id=t.id, payload=CommunicationTaskUpdate(priority="HIGH"), db=db, actor=alice)
            with self.assertRaises(HTTPException):
                comm.delete_task(task_id=t.id, db=db, viewer=alice)
            # The involved person can still open a task they just closed.
            comm.update_task(task_id=t.id, payload=CommunicationTaskUpdate(status="DONE"), db=db, actor=bob)
            self.assertEqual(comm.get_task(task_id=t.id, db=db, viewer=bob).status, "DONE")

    def test_dashboard_counts_match_the_scoped_list(self):
        with _temp_db() as db:
            admin = _user(db, "admin", Role.ADMIN)
            alice = _user(db, "alice")
            past = datetime.utcnow() - timedelta(days=2)
            _task(db, "a1", assigned_to_user_id=alice.id, due_date=past, signal="BLACK")
            _task(db, "a2", assigned_to_user_id=alice.id, status="IN_PROGRESS")
            _task(db, "a3", assigned_to_user_id=alice.id, status="DONE")
            _task(db, "other", status="TODO", due_date=past)

            mine = comm.tasks_dashboard(db=db, viewer=alice)
            self.assertEqual(mine["total_tasks"], len(comm.tasks_index(db=db, overdue=False, limit=500, viewer=alice)))
            self.assertEqual(mine["total_tasks"], 2)
            self.assertEqual(mine["done"], 0)
            self.assertEqual(mine["overdue"], 1)
            self.assertEqual(mine["critical"], 1)

            allc = comm.tasks_dashboard(db=db, viewer=admin)
            self.assertEqual(allc["total_tasks"], 4)
            self.assertEqual(allc["done"], 1)
            self.assertEqual(allc["overdue"], 2)
            self.assertEqual(allc["in_progress"], 1)

    def test_analytics_scoped_for_non_admin(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            _task(db, "a1", assigned_to_user_id=alice.id)
            _task(db, "other")
            data = comm.task_analytics_summary(db=db, viewer=alice)
            self.assertEqual(data["totals"]["total"], 1)

    def test_hub_task_panel_is_scoped(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            _task(db, "mine", supplier_po_no="P1", assigned_to_user_id=alice.id)
            _task(db, "theirs", supplier_po_no="P1")
            grouped = hub.get_hub_tasks(supplier_po_no="P1", db=db, viewer=alice)
            titles = {t["title"] for grp in grouped.values() for t in grp}
            self.assertEqual(titles, {"mine"})
            self.assertEqual(hub.comm_dashboard(db=db, viewer=alice)["open_tasks"], 1)

    def test_employee_is_never_admin(self):
        with _temp_db() as db:
            emp = _user(db, "emp", Role.ADMIN, emp_code="E1")
            self.assertFalse(task_visibility.is_task_admin(emp))


class TaskNotificationTests(unittest.TestCase):
    def test_create_notifies_assignee_and_watchers_only(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            bob = _user(db, "bob")
            carol = _user(db, "carol")
            emp = _user(db, "emp", Role.EMPLOYEE, emp_code="E1")
            stranger = _user(db, "stranger", Role.MANAGER)
            admin = _user(db, "admin", Role.ADMIN)

            task = comm.create_task(
                payload=CommunicationTaskCreate(
                    title="Ship it", assigned_to_user_id=bob.id, watchers=[carol.id, emp.id]),
                db=db, actor=alice,
            )
            self.assertEqual(task.created_by_user_id, alice.id)
            self.assertEqual(len(_notes(db, alice)), 0, "the actor is never notified")
            self.assertEqual(len(_notes(db, stranger)), 0, "no broadcast")
            self.assertEqual(len(_notes(db, admin)), 0, "no broadcast to admins either")
            self.assertEqual(_notes(db, bob)[0].type, "TASK_ASSIGNED")
            self.assertEqual(_notes(db, bob)[0].link, f"/tasks?task={task.id}")
            self.assertEqual(_notes(db, carol)[0].type, "TASK_CREATED")
            self.assertEqual(_notes(db, emp)[0].link, f"/eportal/tasks?task={task.id}")

    def test_create_with_background_tasks_defers_the_fan_out(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            bob = _user(db, "bob")

            class FakeBG:
                def __init__(self):
                    self.calls = []

                def add_task(self, fn, *args, **kwargs):
                    self.calls.append((fn, args, kwargs))

            bg = FakeBG()
            task = comm.create_task(
                payload=CommunicationTaskCreate(title="x", assigned_to_user_id=bob.id),
                db=db, actor=alice, background_tasks=bg,
            )
            self.assertEqual(len(bg.calls), 1, "queued, not sent inline")
            self.assertEqual(len(_notes(db, bob)), 0)
            self.assertEqual(bg.calls[0][1][1], task.id)

    def test_status_change_and_comment_notify_involved_people(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            bob = _user(db, "bob")
            stranger = _user(db, "stranger")
            task = comm.create_task(
                payload=CommunicationTaskCreate(title="x", assigned_to_user_id=bob.id), db=db, actor=alice)
            comm.update_task(task_id=task.id, payload=CommunicationTaskUpdate(status="IN_PROGRESS"), db=db, actor=bob)
            self.assertEqual([n.type for n in _notes(db, alice)], ["TASK_UPDATED"])
            comm.add_task_comment(task_id=task.id, body={"comment": "on it"}, db=db, actor=bob)
            self.assertEqual(sorted(n.type for n in _notes(db, alice)), ["TASK_COMMENT", "TASK_UPDATED"])
            self.assertEqual(len(_notes(db, stranger)), 0)

    def test_reassign_notifies_new_assignee(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            bob = _user(db, "bob")
            carol = _user(db, "carol")
            task = comm.create_task(
                payload=CommunicationTaskCreate(title="x", assigned_to_user_id=bob.id), db=db, actor=alice)
            comm.update_task(
                task_id=task.id, payload=CommunicationTaskUpdate(assigned_to_user_id=carol.id), db=db, actor=alice)
            self.assertEqual(_notes(db, carol)[0].type, "TASK_ASSIGNED")


class MyTasksExportTests(unittest.TestCase):
    def test_export_contains_only_my_tasks(self):
        from openpyxl import load_workbook

        with _temp_db() as db:
            admin = _user(db, "admin", Role.ADMIN)
            alice = _user(db, "alice")
            _task(db, "mine", assigned_to_user_id=alice.id)
            _task(db, "mine-done", assigned_to_user_id=alice.id, status="DONE")
            _task(db, "theirs")
            _task(db, "admins-own", created_by_user_id=admin.id, status="DONE")

            def titles(user):
                wb = load_workbook(io.BytesIO(comm.my_tasks_workbook(db, user)))
                return [r[1] for r in wb.active.iter_rows(min_row=2, values_only=True)]

            self.assertEqual(titles(alice), ["mine"])
            # Admin "My tasks" = their own involvement, including completed.
            self.assertEqual(titles(admin), ["admins-own"])
            resp = comm.export_my_tasks(db=db, viewer=alice)
            self.assertIn("my-tasks-", resp.headers["content-disposition"])

    def test_employee_export_route(self):
        with _temp_db() as db:
            emp = _user(db, "emp", Role.EMPLOYEE, emp_code="E1")
            _task(db, "mine", assigned_to_user_id=emp.id)
            resp = employee_portal.export_my_tasks(user=emp, db=db)
            self.assertIn("spreadsheetml", resp.media_type)


class SourceMailContextTests(unittest.TestCase):
    def _mail_with_file(self, db):
        cm = CommunicationMessage(
            direction="INCOMING", status="RECEIVED", channel="EMAIL",
            subject="Dispatch delayed", body="Dear team, dispatch moves to Friday.",
            sender_email="vendor@acme.com", supplier_name="ACME", supplier_po_no="PO-9",
            received_at=datetime(2026, 11, 10, 9, 30),
        )
        db.add(cm)
        db.commit()
        db.refresh(cm)
        att = MessageAttachment(
            message_id=cm.id, filename="challan.pdf", content_type="application/pdf",
            size_bytes=10, storage_key="k/challan.pdf", uploaded_by_kind="system",
        )
        db.add(att)
        db.commit()
        db.refresh(att)
        return cm, att

    def test_task_from_mail_carries_context_and_attachments(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            cm, att = self._mail_with_file(db)
            created = hub.create_hub_task(
                CommunicationTaskCreate(title="Follow up", source_message_id=cm.id),
                db=db, actor=alice,
            )
            task = db.get(CommunicationTask, created["id"])
            self.assertEqual(task.source_message_id, cm.id)
            self.assertEqual(task.supplier_po_no, "PO-9", "linkage filled from the mail")
            self.assertEqual(task.created_by_user_id, alice.id)

            src = comm.task_source_message(task_id=task.id, db=db, viewer=alice)["source"]
            self.assertEqual(src["subject"], "Dispatch delayed")
            self.assertEqual(src["sender"], "vendor@acme.com")
            self.assertIn("Friday", src["body_excerpt"])
            self.assertEqual([a["id"] for a in src["attachments"]], [att.id])
            # Referenced, not copied: the file still belongs to the mail only.
            db.refresh(att)
            self.assertEqual(att.message_id, cm.id)
            self.assertIsNone(att.task_id)

    def test_unknown_source_message_is_dropped(self):
        with _temp_db() as db:
            alice = _user(db, "alice")
            task = comm.create_task(
                payload=CommunicationTaskCreate(title="x", source_message_id=99999), db=db, actor=alice)
            self.assertIsNone(task.source_message_id)

    def test_employee_can_download_source_mail_file_of_a_visible_task(self):
        with _temp_db() as db:
            emp = _user(db, "emp", Role.EMPLOYEE, emp_code="E1")
            other = _user(db, "other", Role.EMPLOYEE, emp_code="E2")
            cm, att = self._mail_with_file(db)
            _task(db, "from mail", source_message_id=cm.id, assigned_to_user_id=emp.id)
            with patch("app.routers.attachments.attachment_service.get_bytes", return_value=b"%PDF"):
                resp = employee_portal.download_attachment(att.id, user=emp, db=db)
                self.assertEqual(resp.body, b"%PDF")
                with self.assertRaises(HTTPException):
                    employee_portal.download_attachment(att.id, user=other, db=db)


class EmployeeCreateTests(unittest.TestCase):
    def test_po_short_ref_and_hash_are_accepted(self):
        with _temp_db() as db:
            emp = _user(db, "emp", Role.EMPLOYEE, emp_code="E1")
            db.add(ProcurementRecord(
                crm_no="C1", material_name="W", supplier_po_no="2627-00042",
                po_short_ref="45021", supplier_name="ACME", owner_emp_code="E1",
            ))
            db.commit()
            t = employee_portal.create_task(
                CommunicationTaskCreate(title="x", supplier_po_no="#45021"), user=emp, db=db)
            self.assertEqual(t.supplier_po_no, "2627-00042")
            self.assertIn(t.id, [x.id for x in employee_portal.my_tasks(user=emp, db=db)])


if __name__ == "__main__":
    unittest.main()
