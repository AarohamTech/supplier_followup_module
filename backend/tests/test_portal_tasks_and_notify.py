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
from app.schemas.communication_task import (  # noqa: E402
    CommunicationTaskCreate,
    CommunicationTaskUpdate,
)
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

    def test_orphan_fallback_skips_employee_portal_accounts(self):
        # Regression: an employee bell must stay scoped to the employee's own
        # POs. An orphan-PO broadcast must reach real staff but NOT a random
        # employee-portal account who doesn't own the PO.
        with _temp_db() as db:
            _po(db, po="PO-ORPHAN", owner=None)  # no owner, no tasks
            staff = user_service.create_user(
                db, email="mgr@corp.com", password="x" * 8, role=Role.MANAGER)
            stranger_emp = user_service.create_user(
                db, email="emp@corp.com", password="x" * 8, role=Role.EMPLOYEE,
                emp_code="EMPX", username="EMPX")
            notification_service.notify_po_owners(
                db, supplier_po_no="PO-ORPHAN", type="X", title="hi")
            self.assertEqual(notification_service.unread_count(db, staff.id), 1)
            self.assertEqual(notification_service.unread_count(db, stranger_emp.id), 0)

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

    def test_full_update_scoped_to_owned_po_or_assigned(self):
        with _temp_db() as db:
            emp = self._emp(db)
            _po(db, po="OWNED", owner="EMP1")
            _po(db, po="FOREIGN", owner="OTHER")
            on_owned = CommunicationTask(
                title="on owned", supplier_po_no="OWNED", status="TODO", watchers=[])
            foreign = CommunicationTask(
                title="foreign", supplier_po_no="FOREIGN", status="TODO", watchers=[])
            db.add_all([on_owned, foreign])
            db.commit()
            db.refresh(on_owned)
            db.refresh(foreign)

            # Full field update allowed on a task on the employee's own PO.
            out = employee_portal.update_my_task(
                on_owned.id,
                CommunicationTaskUpdate(status="DONE", priority="HIGH", signal="RED"),
                user=emp, db=db)
            self.assertEqual(out.status, "DONE")
            self.assertEqual(out.priority, "HIGH")
            self.assertEqual(out.signal, "RED")
            self.assertEqual(out.progress_percent, 100)
            db.refresh(on_owned)
            self.assertIsNotNone(on_owned.closed_at)

            # A task on a PO they don't own and aren't assigned to → 404.
            from fastapi import HTTPException
            with self.assertRaises(HTTPException):
                employee_portal.update_my_task(
                    foreign.id, CommunicationTaskUpdate(status="DONE"), user=emp, db=db)

    def test_create_only_on_owned_po(self):
        from fastapi import HTTPException
        with _temp_db() as db:
            emp = self._emp(db)
            _po(db, po="OWNED", owner="EMP1")
            t = employee_portal.create_task(
                CommunicationTaskCreate(title="new", supplier_po_no="OWNED"), user=emp, db=db)
            self.assertEqual(t.supplier_po_no, "OWNED")
            self.assertEqual(t.assigned_by, emp.full_name or emp.username or emp.email)
            # Cannot create on a PO the employee doesn't own.
            with self.assertRaises(HTTPException):
                employee_portal.create_task(
                    CommunicationTaskCreate(title="bad", supplier_po_no="FOREIGN"), user=emp, db=db)


class SupplierTaskScopeTests(unittest.TestCase):
    def test_supplier_tasks_scoped_and_sanitized(self):
        with _temp_db() as db:
            s = SupplierMaster(supplier_name="ACME TOOLS", is_active=True)
            db.add(s)
            db.commit()
            db.refresh(s)
            sup = user_service.create_user(
                db, email="sup@acme.com", password="x" * 8, role=Role.SUPPLIER, supplier_id=s.id)
            db.add(CommunicationTask(
                title="for acme", supplier_id=s.id, supplier_name="ACME TOOLS",
                supplier_po_no="PO-1", status="TODO", watchers=[42],
                assigned_to="Internal Staffer", assigned_to_user_id=7, ai_summary="internal note"))
            db.add(CommunicationTask(
                title="for beta", supplier_id=999, supplier_name="BETA PARTS",
                supplier_po_no="PO-2", status="TODO", watchers=[]))
            db.commit()

            tasks = portal.supplier_tasks(user=sup, db=db)
            self.assertEqual({t.title for t in tasks}, {"for acme"})
            # Internal fields must be stripped before reaching a supplier.
            t = tasks[0]
            self.assertIsNone(t.assigned_to)
            self.assertIsNone(t.assigned_to_user_id)
            self.assertEqual(t.watchers, [])
            self.assertIsNone(t.ai_summary)


class PortalCommsUnreadTests(unittest.TestCase):
    def test_employee_unread_count_and_mark_read(self):
        with _temp_db() as db:
            emp = user_service.create_user(
                db, email="EMP1@corp.com", password="x" * 8, role=Role.EMPLOYEE,
                emp_code="EMP1", username="EMP1")
            _po(db, po="OWNED", owner="EMP1")
            db.add(CommunicationMessage(
                direction="INCOMING", status="RECEIVED", channel="EMAIL",
                supplier_po_no="OWNED", supplier_name="ACME TOOLS", body="supplier reply"))
            db.commit()

            item = {p.supplier_po_no: p for p in employee_portal.list_pos(user=emp, db=db).items}["OWNED"]
            self.assertEqual(item.unread_inbound, 1)
            self.assertEqual(employee_portal.mark_messages_read("OWNED", user=emp, db=db)["marked"], 1)
            item2 = {p.supplier_po_no: p for p in employee_portal.list_pos(user=emp, db=db).items}["OWNED"]
            self.assertEqual(item2.unread_inbound, 0)

    def test_supplier_unread_count_and_mark_read(self):
        with _temp_db() as db:
            s = SupplierMaster(supplier_name="ACME TOOLS", is_active=True)
            db.add(s)
            db.commit()
            db.refresh(s)
            sup = user_service.create_user(
                db, email="sup@acme.com", password="x" * 8, role=Role.SUPPLIER, supplier_id=s.id)
            _po(db, po="PO-1", name="ACME TOOLS")
            db.add(CommunicationMessage(
                direction="OUTGOING", status="SENT", channel="EMAIL",
                supplier_id=s.id, supplier_name="ACME TOOLS", supplier_po_no="PO-1", body="from buyer"))
            db.commit()

            item = {p.supplier_po_no: p for p in portal.list_pos(user=sup, db=db).items}["PO-1"]
            self.assertEqual(item.unread_inbound, 1)
            self.assertEqual(portal.mark_po_messages_read("PO-1", user=sup, db=db)["marked"], 1)
            item2 = {p.supplier_po_no: p for p in portal.list_pos(user=sup, db=db).items}["PO-1"]
            self.assertEqual(item2.unread_inbound, 0)


if __name__ == "__main__":
    unittest.main()
