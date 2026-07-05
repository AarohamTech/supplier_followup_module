"""Shared PO views: grouped list (all vs scoped), per-PO detail, admin router RBAC."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_po_view.sqlite")

import unittest
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_mod
from app.database import Base, get_db
from app.models import CommunicationMessage, ProcurementRecord
from app.services import company_service, po_view_service as pv, user_service


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


def _po_line(db, *, crm, po="PO1", supplier="Acme", owner="E1", signal="GREEN"):
    db.add(ProcurementRecord(
        crm_no=crm, material_name=f"M-{crm}", supplier_po_no=po, supplier_name=supplier,
        owner_emp_code=owner, signal=signal,
    ))
    db.commit()


class ServiceTests(unittest.TestCase):
    def test_list_groups_all_vs_scoped(self):
        with _temp_db() as db:
            _po_line(db, crm="C1", po="PO1", owner="E1")
            _po_line(db, crm="C2", po="PO1", owner="E1")   # same PO, groups into one
            _po_line(db, crm="C3", po="PO2", owner="E2")

            all_groups = pv.list_groups(db)
            self.assertEqual({g["supplier_po_no"] for g in all_groups}, {"PO1", "PO2"})
            po1 = [g for g in all_groups if g["supplier_po_no"] == "PO1"][0]
            self.assertEqual(po1["material_count"], 2)

            scoped = pv.list_groups(db, owner_emp_code="E1")
            self.assertEqual({g["supplier_po_no"] for g in scoped}, {"PO1"})

    def test_pagination_and_search(self):
        with _temp_db() as db:
            for i in range(1, 8):  # PO1..PO7, one line each
                _po_line(db, crm=f"C{i}", po=f"PO{i}", supplier="Acme")

            items, total = pv.grouped_pos(db, page=1, size=3)
            self.assertEqual(total, 7)
            self.assertEqual(len(items), 3)
            last, _ = pv.grouped_pos(db, page=3, size=3)
            self.assertEqual(len(last), 1)  # 7 groups → 3 + 3 + 1

            found, ftotal = pv.grouped_pos(db, search="PO5")
            self.assertEqual(ftotal, 1)
            self.assertEqual(found[0]["supplier_po_no"], "PO5")

    def test_po_detail_materials_and_messages(self):
        with _temp_db() as db:
            _po_line(db, crm="C1", po="PO1", supplier="Acme", owner="E1")
            db.add(CommunicationMessage(
                direction="INCOMING", status="RECEIVED", supplier_name="Acme",
                supplier_po_no="PO1", subject="Re: PO1", body="dispatch soon",
            ))
            db.commit()

            detail = pv.po_detail(db, supplier_po_no="PO1", supplier_name="Acme")
            self.assertEqual(len(detail["materials"]), 1)
            self.assertEqual(len(detail["messages"]), 1)
            self.assertEqual(detail["messages"][0]["direction"], "INCOMING")
            self.assertEqual(detail["messages"][0]["subject"], "Re: PO1")

            # owner scoping: E2 doesn't own PO1 -> None (404 upstream)
            self.assertIsNone(pv.po_detail(db, supplier_po_no="PO1", supplier_name="Acme", owner_emp_code="E2"))
            self.assertIsNotNone(pv.po_detail(db, supplier_po_no="PO1", supplier_name="Acme", owner_emp_code="E1"))


class RouterRbacTests(unittest.TestCase):
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
        return r.json()["access_token"]

    def test_admin_only(self):
        admin = self._token("admin@x.com", "admin")
        manager = self._token("mgr@x.com", "manager")
        _po_line(self.db, crm="C1", po="PO1", owner="E1")

        ok = self.client.get("/api/po-view/pos", headers={"Authorization": f"Bearer {admin}"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(any(p["supplier_po_no"] == "PO1" for p in ok.json()["items"]))

        blocked = self.client.get("/api/po-view/pos", headers={"Authorization": f"Bearer {manager}"})
        self.assertEqual(blocked.status_code, 403, blocked.text)

        # cancel sets the whole PO pending
        cancel = self.client.post(
            "/api/po-view/pos/PO1/request-cancel?supplier_name=Acme",
            headers={"Authorization": f"Bearer {admin}"},
        )
        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertEqual(cancel.json()["cancellation_status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
