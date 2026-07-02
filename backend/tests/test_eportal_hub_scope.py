"""Security-boundary tests for the employee-scoped Communication Hub.

Every endpoint must only ever surface / mutate data on POs the employee owns
(ProcurementRecord.owner_emp_code == user.emp_code). Anything else → 404.

Uses the in-memory SQLite pattern: call the route functions directly with a
constructed User + Session. Production data is never touched."""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_eportal_hub.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402,F401
    CommunicationMessage,
    CommunicationTask,
    HiAgentChatMessage,
    MailHistory,
    Notification,
    ProcurementRecord,
    SupplierMaster,
    User,
)
from app.routers import eportal_hub as hub  # noqa: E402
from app.schemas.communication_task import (  # noqa: E402
    CommunicationTaskCreate,
    CommunicationTaskUpdate,
)
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


def _po(db, *, po, name, owner, signal="RED", material="Widget"):
    rec = ProcurementRecord(
        crm_no=f"CRM-{po}", material_name=material, supplier_po_no=po,
        supplier_name=name, owner_emp_code=owner, signal=signal,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _emp(db, emp_code):
    return user_service.create_user(
        db, email=f"{emp_code}@corp.com", password="x" * 8, role=Role.EMPLOYEE,
        emp_code=emp_code, username=emp_code,
    )


class SupplierAndPoIsolationTests(unittest.TestCase):
    def test_suppliers_and_pos_isolated_between_employees(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            emp2 = _emp(db, "EMP2")
            # EMP1 owns ACME's PO-A1; EMP2 owns BETA's PO-B1.
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1")
            _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2")

            s1 = hub.list_suppliers(user=emp1, db=db)
            self.assertEqual({s["supplier_name"].upper() for s in s1}, {"ACME TOOLS"})
            s2 = hub.list_suppliers(user=emp2, db=db)
            self.assertEqual({s["supplier_name"].upper() for s in s2}, {"BETA PARTS"})

            # POs list scoped to each employee's owned PO only.
            p1 = hub.list_pos(supplier_name="ACME TOOLS", user=emp1, db=db)
            self.assertEqual({p["supplier_po_no"] for p in p1}, {"PO-A1"})
            # EMP1 asking for BETA (which they don't own) sees nothing.
            self.assertEqual(hub.list_pos(supplier_name="BETA PARTS", user=emp1, db=db), [])

            p2 = hub.list_pos(supplier_name="BETA PARTS", user=emp2, db=db)
            self.assertEqual({p["supplier_po_no"] for p in p2}, {"PO-B1"})
            self.assertEqual(hub.list_pos(supplier_name="ACME TOOLS", user=emp2, db=db), [])

    def test_shared_supplier_only_owned_pos_surface(self):
        # Both employees buy from ACME, but each only sees their own PO.
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            emp2 = _emp(db, "EMP2")
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1")
            _po(db, po="PO-A2", name="ACME TOOLS", owner="EMP2")

            p1 = hub.list_pos(supplier_name="ACME TOOLS", user=emp1, db=db)
            self.assertEqual({p["supplier_po_no"] for p in p1}, {"PO-A1"})
            p2 = hub.list_pos(supplier_name="ACME TOOLS", user=emp2, db=db)
            self.assertEqual({p["supplier_po_no"] for p in p2}, {"PO-A2"})

            # Supplier aggregate (open_po_count) reflects only owned POs.
            entry = hub.list_suppliers(user=emp1, db=db)[0]
            self.assertEqual(entry["open_po_count"], 1)

    def test_dashboard_counts_scoped(self):
        with _temp_db() as db:
            emp1 = _emp(db, "EMP1")
            _po(db, po="PO-A1", name="ACME TOOLS", owner="EMP1", signal="RED")
            _po(db, po="PO-B1", name="BETA PARTS", owner="EMP2", signal="BLACK")
            d = hub.dashboard(user=emp1, db=db)
            self.assertEqual(d["active_pos"], 1)
            self.assertEqual(d["active_suppliers"], 1)
            self.assertEqual(d["delayed_pos"], 1)  # only EMP1's RED PO


class ForeignPoRaises404Tests(unittest.TestCase):
    def setUp(self):
        self.ctx = _temp_db()
        self.db = self.ctx.__enter__()
        self.emp = _emp(self.db, "EMP1")
        # Owned + foreign POs.
        self.owned = _po(self.db, po="OWNED", name="ACME TOOLS", owner="EMP1")
        self.foreign = _po(self.db, po="FOREIGN", name="BETA PARTS", owner="EMP2")

    def tearDown(self):
        self.ctx.__exit__(None, None, None)

    def _assert_404(self, fn, *args, **kwargs):
        with self.assertRaises(HTTPException) as cm:
            fn(*args, **kwargs)
        self.assertEqual(cm.exception.status_code, 404)

    def test_thread_foreign_404(self):
        self._assert_404(hub.get_thread, supplier_po_no="FOREIGN", user=self.emp, db=self.db)
        self._assert_404(
            hub.get_thread, procurement_record_id=self.foreign.id, user=self.emp, db=self.db
        )

    def test_mark_read_foreign_404(self):
        self._assert_404(hub.mark_thread_read, supplier_po_no="FOREIGN", user=self.emp, db=self.db)

    def test_tasks_foreign_404(self):
        self._assert_404(hub.get_tasks, supplier_po_no="FOREIGN", user=self.emp, db=self.db)

    def test_create_task_foreign_404(self):
        self._assert_404(
            hub.create_task,
            CommunicationTaskCreate(title="bad", supplier_po_no="FOREIGN"),
            user=self.emp, db=self.db,
        )

    def test_update_task_foreign_404(self):
        # A task on a PO the employee does not own.
        t = CommunicationTask(title="foreign", supplier_po_no="FOREIGN", status="TODO", watchers=[])
        self.db.add(t)
        self.db.commit()
        self.db.refresh(t)
        self._assert_404(
            hub.update_task, t.id, CommunicationTaskUpdate(status="DONE"),
            user=self.emp, db=self.db,
        )

    def test_update_missing_task_404(self):
        self._assert_404(
            hub.update_task, 999999, CommunicationTaskUpdate(status="DONE"),
            user=self.emp, db=self.db,
        )

    def test_reply_foreign_404(self):
        payload = hub.hub.HubReplyIn(supplier_po_no="FOREIGN", body="hi", send_email=False)
        self._assert_404(hub.reply_now, payload, user=self.emp, db=self.db)

    def test_escalate_foreign_404(self):
        self._assert_404(
            hub.escalate, procurement_record_id=self.foreign.id, user=self.emp, db=self.db
        )

    def test_ai_reply_foreign_404(self):
        self._assert_404(
            hub.ai_reply, procurement_record_id=self.foreign.id, user=self.emp, db=self.db
        )

    def test_commitments_foreign_404(self):
        self._assert_404(
            hub.list_commitments, supplier_po_no="FOREIGN", user=self.emp, db=self.db
        )

    def test_send_mail_foreign_404(self):
        mh = MailHistory(
            procurement_record_id=self.foreign.id,
            supplier_po_no="FOREIGN", supplier_name="BETA PARTS",
            material_name="Widget",
            subject="x", body="y", mail_type="HUB_REPLY", sent_status="DRAFT",
        )
        self.db.add(mh)
        self.db.commit()
        self.db.refresh(mh)
        self._assert_404(hub.send_mail_now, mail_history_id=mh.id, user=self.emp, db=self.db)

    def test_agent_foreign_404(self):
        payload = hub.hub.HubAgentIn(message="summarise", supplier_po_no="FOREIGN")
        self._assert_404(hub.run_agent, payload, user=self.emp, db=self.db)

    def test_agent_customer_thread_404(self):
        payload = hub.hub.HubAgentIn(message="summarise", customer_mail_id=5)
        self._assert_404(hub.run_agent, payload, user=self.emp, db=self.db)

    def test_message_approve_foreign_404(self):
        cm = CommunicationMessage(
            direction="OUTGOING", status="DRAFT", channel="EMAIL",
            supplier_po_no="FOREIGN", supplier_name="BETA PARTS", body="draft",
        )
        self.db.add(cm)
        self.db.commit()
        self.db.refresh(cm)
        self._assert_404(hub.approve_message, cm.id, user=self.emp, db=self.db)


class OwnedPoSucceedsTests(unittest.TestCase):
    def test_create_and_update_on_owned_po(self):
        with _temp_db() as db:
            emp = _emp(db, "EMP1")
            _po(db, po="OWNED", name="ACME TOOLS", owner="EMP1")

            created = hub.create_task(
                CommunicationTaskCreate(title="new", supplier_po_no="OWNED"),
                user=emp, db=db,
            )
            self.assertEqual(created["supplier_po_no"], "OWNED")
            self.assertEqual(created["title"], "new")
            # Created via shared staff logic → assigned_by stamped with the actor.
            self.assertEqual(created["assigned_by"], emp.full_name or emp.username or emp.email)

            updated = hub.update_task(
                created["id"], CommunicationTaskUpdate(status="DONE", priority="P1"),
                user=emp, db=db,
            )
            self.assertEqual(updated["status"], "DONE")
            self.assertEqual(updated["priority"], "P1")
            self.assertIsNotNone(updated["closed_at"])

    def test_tasks_grouped_on_owned_po(self):
        with _temp_db() as db:
            emp = _emp(db, "EMP1")
            _po(db, po="OWNED", name="ACME TOOLS", owner="EMP1")
            db.add(CommunicationTask(
                title="t1", supplier_po_no="OWNED", status="TODO", watchers=[]))
            db.add(CommunicationTask(
                title="t2", supplier_po_no="OWNED", status="DONE", watchers=[]))
            # A foreign task must NOT leak into the grouped result.
            db.add(CommunicationTask(
                title="foreign", supplier_po_no="FOREIGN", status="TODO", watchers=[]))
            db.commit()

            grouped = hub.get_tasks(supplier_po_no="OWNED", user=emp, db=db)
            self.assertEqual({t["title"] for t in grouped["todo"]}, {"t1"})
            self.assertEqual({t["title"] for t in grouped["done"]}, {"t2"})

            # No PO filter → union of owned POs only (foreign excluded).
            all_grouped = hub.get_tasks(user=emp, db=db)
            titles = {t["title"] for grp in all_grouped.values() for t in grp}
            self.assertEqual(titles, {"t1", "t2"})

    def test_thread_on_owned_po_returns_shape(self):
        with _temp_db() as db:
            emp = _emp(db, "EMP1")
            rec = _po(db, po="OWNED", name="ACME TOOLS", owner="EMP1")
            db.add(CommunicationMessage(
                direction="INCOMING", status="RECEIVED", channel="EMAIL",
                supplier_po_no="OWNED", supplier_name="ACME TOOLS", body="supplier reply",
                procurement_record_id=rec.id))
            db.commit()
            thread = hub.get_thread(supplier_po_no="OWNED", user=emp, db=db)
            # Same shape keys as the admin hub thread.
            for key in ("thread_id", "supplier_po_no", "signal", "risk_level", "messages"):
                self.assertIn(key, thread)
            self.assertEqual(thread["supplier_po_no"], "OWNED")

    def test_agent_history_is_scoped_to_owned_po(self):
        with _temp_db() as db:
            emp = _emp(db, "EMP1")
            owned = _po(db, po="OWNED", name="ACME TOOLS", owner="EMP1")
            foreign = _po(db, po="FOREIGN", name="ACME TOOLS", owner="EMP2")
            db.add(HiAgentChatMessage(
                thread_id=str(owned.id), procurement_record_id=owned.id,
                user_id=emp.id, role="user", content="remember me", actions=[],
            ))
            db.commit()

            out = hub.get_agent_history(
                procurement_record_id=owned.id, user=emp, db=db,
            )
            self.assertEqual(out["thread_id"], str(owned.id))
            self.assertEqual(out["messages"][0]["text"], "remember me")
            with self.assertRaises(HTTPException) as ctx:
                hub.get_agent_history(
                    procurement_record_id=foreign.id, user=emp, db=db,
                )
            self.assertEqual(ctx.exception.status_code, 404)

    def test_mark_read_on_owned_po(self):
        with _temp_db() as db:
            emp = _emp(db, "EMP1")
            _po(db, po="OWNED", name="ACME TOOLS", owner="EMP1")
            db.add(CommunicationMessage(
                direction="INCOMING", status="RECEIVED", channel="EMAIL",
                supplier_po_no="OWNED", supplier_name="ACME TOOLS", body="reply"))
            db.commit()
            out = hub.mark_thread_read(supplier_po_no="OWNED", user=emp, db=db)
            self.assertEqual(out["marked"], 1)


if __name__ == "__main__":
    unittest.main()
