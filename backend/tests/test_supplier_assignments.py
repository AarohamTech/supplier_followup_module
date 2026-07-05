"""Supplier -> people assignment: service, incoming-mail routing, and API/RBAC."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_supplier_assignments.sqlite")

import unittest
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_mod
from app.database import Base, get_db
from app.models import (
    CommunicationMessage,
    Notification,
    SupplierAssignment,  # noqa: F401
    SupplierEmail,
    SupplierMaster,
    User,
)
from app.services import company_service, supplier_assignment_service as svc, user_service
from app.workers import mail_fetch_worker


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


def _staff(db, email, role="user", name=None):
    u = User(email=email, hashed_password="x", role=role, full_name=name or email)
    db.add(u); db.commit(); db.refresh(u)
    return u


class ServiceTests(unittest.TestCase):
    def test_assignable_includes_staff_and_employees_excludes_suppliers(self):
        with _temp_db() as db:
            _staff(db, "a@c.test")
            db.add(User(email="emp@c.test", hashed_password="x", role="employee", emp_code="E1"))
            db.add(User(email="sup@x.com", hashed_password="x", role="supplier", supplier_id=1))
            db.commit()
            emails = {u.email for u in svc.assignable_users(db)}
            # staff + employees are assignable; only the external supplier login is not
            self.assertEqual(emails, {"a@c.test", "emp@c.test"})

    def test_set_replace_dedupe_and_filter(self):
        with _temp_db() as db:
            s = SupplierMaster(supplier_name="Acme"); db.add(s); db.commit()
            u1 = _staff(db, "a@c.test"); u2 = _staff(db, "b@c.test")
            # dupes collapse; unknown id 999 dropped
            self.assertEqual(svc.set_assignees(db, s.id, [u1.id, u2.id, u1.id, 999]), [u1.id, u2.id])
            self.assertEqual(svc.get_assignee_ids(db, s.id), [u1.id, u2.id])
            # replace
            self.assertEqual(svc.set_assignees(db, s.id, [u2.id]), [u2.id])
            self.assertEqual(svc.get_assignee_ids(db, s.id), [u2.id])
            # clear
            self.assertEqual(svc.set_assignees(db, s.id, []), [])


class RoutingTests(unittest.TestCase):
    def test_incoming_supplier_mail_assigns_and_notifies(self):
        with _temp_db() as db:
            s = SupplierMaster(supplier_name="Acme"); db.add(s); db.commit()
            db.add(SupplierEmail(
                supplier_id=s.id, supplier_name="Acme",
                to_emails=["sales@acme.test"], cc_emails=[], bcc_emails=[], escalation_emails=[],
                is_active=True,
            ))
            u1 = _staff(db, "a@c.test"); u2 = _staff(db, "b@c.test")
            db.commit()
            svc.set_assignees(db, s.id, [u1.id, u2.id])

            raw = (
                b"From: Acme Sales <sales@acme.test>\r\n"
                b"To: stores@ours.test\r\n"
                b"Subject: Re: PO update\r\n"
                b"Message-ID: <abc123@acme.test>\r\n"
                b"Date: Mon, 5 Jul 2026 10:00:00 +0000\r\n"
                b"\r\n"
                b"We will dispatch next week.\r\n"
            )
            result = mail_fetch_worker._process_one(db, b"1", raw)
            self.assertFalse(result["skipped"])
            self.assertEqual(result["supplier_id"], s.id)

            msg = db.scalars(
                select(CommunicationMessage).where(
                    CommunicationMessage.message_uid == "<abc123@acme.test>"
                )
            ).first()
            self.assertIsNotNone(msg)
            self.assertEqual(sorted(msg.assigned_user_ids or []), sorted([u1.id, u2.id]))

            notes = db.scalars(select(Notification)).all()
            self.assertEqual({n.user_id for n in notes}, {u1.id, u2.id})
            self.assertTrue(all(n.type == "SUPPLIER_MAIL" and n.supplier_id == s.id for n in notes))

    def test_unassigned_supplier_mail_creates_no_notifications(self):
        with _temp_db() as db:
            s = SupplierMaster(supplier_name="Acme"); db.add(s); db.commit()
            db.add(SupplierEmail(
                supplier_id=s.id, supplier_name="Acme",
                to_emails=["sales@acme.test"], cc_emails=[], bcc_emails=[], escalation_emails=[],
                is_active=True,
            ))
            db.commit()
            raw = (
                b"From: sales@acme.test\r\nTo: us@ours.test\r\nSubject: Hi\r\n"
                b"Message-ID: <n1@acme.test>\r\n\r\nbody\r\n"
            )
            mail_fetch_worker._process_one(db, b"1", raw)
            self.assertEqual(db.scalars(select(Notification)).all(), [])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.db = self.Session()
        company_service.seed_companies(self.db)
        main_mod.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(main_mod.app)

    def tearDown(self):
        main_mod.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _token(self, email, role):
        user_service.create_user(self.db, email=email, password="secret123", full_name=role, role=role)
        r = self.client.post("/api/auth/login", json={"email": email, "password": "secret123"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["access_token"]

    def _auth(self, t):
        return {"Authorization": f"Bearer {t}"}

    def test_list_set_and_rbac(self):
        manager = self._token("mgr@x.com", "manager")
        writer = self._token("usr@x.com", "user")
        target = user_service.create_user(self.db, email="agent@x.com", password="p", full_name="Agent", role="user")
        s = SupplierMaster(supplier_name="Acme"); self.db.add(s); self.db.commit(); self.db.refresh(s)

        # list + assignable-users readable by staff
        lst = self.client.get("/api/supplier-assignments", headers=self._auth(writer))
        self.assertEqual(lst.status_code, 200, lst.text)
        self.assertTrue(any(r["supplier_id"] == s.id for r in lst.json()["suppliers"]))
        au = self.client.get("/api/supplier-assignments/assignable-users", headers=self._auth(writer))
        self.assertEqual(au.status_code, 200, au.text)

        # non-manager cannot change assignees
        blocked = self.client.put(
            f"/api/supplier-assignments/{s.id}", headers=self._auth(writer),
            json={"user_ids": [target.id]},
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)

        # manager can
        ok = self.client.put(
            f"/api/supplier-assignments/{s.id}", headers=self._auth(manager),
            json={"user_ids": [target.id]},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual([a["email"] for a in ok.json()["assignees"]], ["agent@x.com"])

        # unknown supplier -> 404
        missing = self.client.put(
            "/api/supplier-assignments/99999", headers=self._auth(manager), json={"user_ids": []}
        )
        self.assertEqual(missing.status_code, 404, missing.text)


if __name__ == "__main__":
    unittest.main()
