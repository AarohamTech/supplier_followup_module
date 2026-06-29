"""Scoped-task endpoints (employee/supplier portals) + PO-owner notification
targeting. DB-backed with in-memory SQLite (production data untouched)."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_portal_tasks.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    Notification,
    ProcurementRecord,
    SupplierMaster,
    User,
)
from app.routers import employee_portal, portal  # noqa: E402
from app.services import notification_service, user_service  # noqa: E402


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


def _po(db, *, po="PO-1", name="ACME TOOLS", owner="EMP1", signal="RED"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{po}", material_name="Widget", supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


class NotifyPoOwnersTests(unittest.TestCase):
    def test_only_po_owner_is_notified_not_all_staff(self):
        with _temp_db() as db:
            _po(db, po="PO-1", owner="EMP1")
            owner = user_service.create_user(
                db, email="owner@corp.com", password="x" * 8, role=Role.USER, emp_code="EMP1")
            other = user_service.create_user(
                db, email="other@corp.com", password="x" * 8, role=Role.MANAGER)

            created = notification_service.notify_po_owners(
                db, supplier_po_no="PO-1", type="SUPPLIER_MESSAGE", title="hi")
            self.assertEqual(created, 1)
            self.assertEqual(notification_service.unread_count(db, owner.id), 1)
            self.assertEqual(notification_service.unread_count(db, other.id), 0)
            # The selector is also written to the row as context.
            row = notification_service.list_for_user(db, owner.id)[0]
            self.assertEqual(row.supplier_po_no, "PO-1")

    def test_open_task_assignee_is_included(self):
        with _temp_db() as db:
            _po(db, po="PO-2", owner=None)
            assignee = user_service.create_user(
                db, email="a@corp.com", password="x" * 8, role=Role.USER)
            db.add(CommunicationTask(
                title="follow up", supplier_po_no="PO-2", status="TODO",
                assigned_to_user_id=assignee.id, watchers=[]))
            db.commit()

            created = notification_service.notify_po_owners(
                db, supplier_po_no="PO-2", type="X", title="hi")
            self.assertEqual(created, 1)
            self.assertEqual(notification_service.unread_count(db, assignee.id), 1)

    def test_orphan_po_falls_back_to_all_staff(self):
        with _temp_db() as db:
            _po(db, po="PO-3", owner=None)  # no owner, no tasks
            staff = user_service.create_user(
                db, email="s@corp.com", password="x" * 8, role=Role.MANAGER)
            notification_service.notify_po_owners(
                db, supplier_po_no="PO-3", type="X", title="hi")
            self.assertEqual(notification_service.unread_count(db, staff.id), 1)

    def test_excluded_sole_owner_does_not_rebroadcast(self):
        with _temp_db() as db:
            _po(db, po="PO-4", owner="EMP9")
            owner = user_service.create_user(
                db, email="o@corp.com", password="x" * 8, role=Role.USER, emp_code="EMP9")
            staff = user_service.create_user(
                db, email="s2@corp.com", password="x" * 8, role=Role.MANAGER)
            created = notification_service.notify_po_owners(
                db, supplier_po_no="PO-4", exclude_user_id=owner.id, type="X", title="hi")
            self.assertEqual(created, 0)  # sole owner excluded → no broadcast
            self.assertEqual(notification_service.unread_count(db, staff.id), 0)


class EmployeeTaskScopeTests(unittest.TestCase):
    def _emp(self, db, emp_code="EMP1"):
        return user_service.create_user(
            db, email=f"{emp_code}@corp.com", password="x" * 8, role=Role.EMPLOYEE,
            emp_code=emp_code, username=emp_code)

    def test_my_tasks_includes_assigned_and_owned_po(self):
        with _temp_db() as db:
            emp = self._emp(db)
            _po(db, po="OWNED", owner="EMP1")
            _po(db, po="FOREIGN", owner="OTHER")
            # On an owned PO (no assignee).
            db.add(CommunicationTask(title="on owned po", supplier_po_no="OWNED", status="TODO", watchers=[]))
            # Assigned to the employee but on someone else's PO.
            db.add(CommunicationTask(
                title="assigned to me", supplier_po_no="FOREIGN", status="TODO",
                assigned_to_user_id=emp.id, watchers=[]))
            # Neither owned nor assigned — must be excluded.
            db.add(CommunicationTask(title="not mine", supplier_po_no="FOREIGN", status="TODO", watchers=[]))
            db.commit()

            tasks = employee_portal.my_tasks(user=emp, db=db)
            titles = {t.title for t in tasks}
            self.assertEqual(titles, {"on owned po", "assigned to me"})

    def test_update_my_task_guarded_to_assignee(self):
        with _temp_db() as db:
            emp = self._emp(db)
            other = self._emp(db, emp_code="EMP2")
            _po(db, po="OWNED", owner="EMP1")
            mine = CommunicationTask(
                title="mine", supplier_po_no="OWNED", status="TODO",
                assigned_to_user_id=emp.id, watchers=[], progress_percent=0)
            theirs = CommunicationTask(
                title="theirs", supplier_po_no="OWNED", status="TODO",
                assigned_to_user_id=other.id, watchers=[])
            db.add_all([mine, theirs])
            db.commit()
            db.refresh(mine)
            db.refresh(theirs)

            out = employee_portal.update_my_task(
                mine.id, employee_portal.EmployeeTaskUpdate(status="DONE"), user=emp, db=db)
            self.assertEqual(out.status, "DONE")
            self.assertEqual(out.progress_percent, 100)
            db.refresh(mine)
            self.assertIsNotNone(mine.closed_at)

            # Cannot touch a task assigned to someone else.
            from fastapi import HTTPException
            with self.assertRaises(HTTPException):
                employee_portal.update_my_task(
                    theirs.id, employee_portal.EmployeeTaskUpdate(status="DONE"), user=emp, db=db)


class SupplierTaskScopeTests(unittest.TestCase):
    def test_supplier_tasks_scoped_to_supplier(self):
        with _temp_db() as db:
            s = SupplierMaster(supplier_name="ACME TOOLS", is_active=True)
            db.add(s)
            db.commit()
            db.refresh(s)
            sup = user_service.create_user(
                db, email="sup@acme.com", password="x" * 8, role=Role.SUPPLIER, supplier_id=s.id)
            db.add(CommunicationTask(
                title="for acme", supplier_id=s.id, supplier_name="ACME TOOLS",
                supplier_po_no="PO-1", status="TODO", watchers=[]))
            db.add(CommunicationTask(
                title="for beta", supplier_id=999, supplier_name="BETA PARTS",
                supplier_po_no="PO-2", status="TODO", watchers=[]))
            db.commit()

            tasks = portal.supplier_tasks(user=sup, db=db)
            self.assertEqual({t.title for t in tasks}, {"for acme"})


if __name__ == "__main__":
    unittest.main()
