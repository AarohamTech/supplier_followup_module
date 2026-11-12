"""Supplier portal logins are scoped by company.

Client report (2026-11): saving SHIVAM ENGINEERS in Email Master showed
"Skipped (conflict): shivam.engineers@rediffmail.com (belongs to another
supplier)". `users` is shared by every company, so the login created for the
same supplier in the OTHER company (different supplier_id) blocked it. Rules:

- the same email in a different company does not block (one login per company)
- a login in this company that points at a stale / same-named supplier is
  re-linked instead of skipped
- two live, different suppliers in one company still conflict, and the
  message names the owner
- supplier ids overlap across companies, so list/deactivate never touch
  another company's logins
"""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_supplier_login_scope.sqlite")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.main as main_mod  # noqa: E402
from app.core.roles import Role  # noqa: E402
from app.core.tenant import use_company  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models.supplier import SupplierMaster  # noqa: E402
from app.models.supplier_email import SupplierEmail  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import company_service, supplier_account_service as svc, user_service  # noqa: E402

EMAIL = "shivam.engineers@rediffmail.com"


@contextmanager
def _db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    company_service.seed_companies(db)
    try:
        with patch.object(svc, "send_credentials_email", return_value=False):
            yield db
    finally:
        db.close()
        engine.dispose()


def _company_id(db, code):
    return company_service.get_by_code(db, code).id


def _supplier_login(db, *, supplier_id, company_id, email=EMAIL, active=True):
    u = user_service.create_user(
        db, email=email, password="secret123", full_name="x", role=Role.SUPPLIER,
        supplier_id=supplier_id, company_id=company_id, is_active=active, check_email=False,
    )
    return u


class CompanyScopeTests(unittest.TestCase):
    def test_same_email_in_other_company_does_not_block(self):
        with _db() as db:
            # Company 101 already has a login for its SHIVAM (id 916).
            other = _supplier_login(db, supplier_id=916, company_id=_company_id(db, "101"))
            s = SupplierMaster(supplier_name="SHIVAM ENGINEERS"); db.add(s); db.commit()
            with use_company("public"):  # company 102
                summary = svc.sync_supplier_logins(
                    db, supplier_id=s.id, supplier_name="SHIVAM ENGINEERS", to_emails=[EMAIL])
            self.assertEqual(summary["conflicts"], [])
            self.assertEqual([c["email"] for c in summary["created"]], [EMAIL])
            logins = user_service.get_all_by_email(db, EMAIL)
            self.assertEqual(len(logins), 2)
            new = next(u for u in logins if u.id != other.id)
            self.assertEqual(new.company_id, _company_id(db, "102"))
            self.assertEqual(new.supplier_id, s.id)
            # The other company's login is untouched.
            db.refresh(other)
            self.assertTrue(other.is_active)
            self.assertEqual(other.supplier_id, 916)

    def test_sync_never_deactivates_another_companys_login_with_same_supplier_id(self):
        with _db() as db:
            s = SupplierMaster(supplier_name="ACME"); db.add(s); db.commit()
            # Company 101's supplier happens to have the same id.
            foreign = _supplier_login(db, supplier_id=s.id, company_id=_company_id(db, "101"),
                                      email="sales@other101.test")
            with use_company("public"):
                summary = svc.sync_supplier_logins(
                    db, supplier_id=s.id, supplier_name="ACME", to_emails=["sales@acme.test"])
                listed = [u.email for u in svc.list_supplier_logins(db, s.id)]
            self.assertEqual(summary["deactivated"], [])
            db.refresh(foreign)
            self.assertTrue(foreign.is_active)
            self.assertEqual(listed, ["sales@acme.test"])

    def test_legacy_null_company_login_counts_as_default_company(self):
        with _db() as db:
            s = SupplierMaster(supplier_name="ACME"); db.add(s); db.commit()
            legacy = _supplier_login(db, supplier_id=s.id, company_id=None, active=False)
            with use_company("public"):
                summary = svc.sync_supplier_logins(
                    db, supplier_id=s.id, supplier_name="ACME", to_emails=[EMAIL])
            self.assertEqual(summary["reactivated"], [EMAIL])
            self.assertEqual(summary["created"], [])
            db.refresh(legacy)
            self.assertTrue(legacy.is_active)


class RelinkAndConflictTests(unittest.TestCase):
    def test_relinks_login_of_a_deleted_supplier(self):
        with _db() as db:
            stale = _supplier_login(db, supplier_id=4242, company_id=_company_id(db, "102"))
            s = SupplierMaster(supplier_name="SHIVAM ENGINEERS"); db.add(s); db.commit()
            with use_company("public"):
                summary = svc.sync_supplier_logins(
                    db, supplier_id=s.id, supplier_name="SHIVAM ENGINEERS", to_emails=[EMAIL])
            self.assertEqual(summary["relinked"], [EMAIL])
            self.assertEqual(summary["conflicts"], [])
            db.refresh(stale)
            self.assertEqual(stale.supplier_id, s.id)
            self.assertTrue(stale.is_active)

    def test_relinks_login_of_same_named_supplier(self):
        with _db() as db:
            old = SupplierMaster(supplier_name="Shivam  Engineers"); db.add(old); db.commit()
            db.add(SupplierEmail(supplier_id=old.id, supplier_name=old.supplier_name,
                                 to_emails=[EMAIL], is_active=True))
            new = SupplierMaster(supplier_name="SHIVAM ENGINEERS"); db.add(new); db.commit()
            login = _supplier_login(db, supplier_id=old.id, company_id=_company_id(db, "102"))
            with use_company("public"):
                summary = svc.sync_supplier_logins(
                    db, supplier_id=new.id, supplier_name="SHIVAM ENGINEERS", to_emails=[EMAIL])
            self.assertEqual(summary["relinked"], [EMAIL])
            db.refresh(login)
            self.assertEqual(login.supplier_id, new.id)

    def test_relinks_when_owner_no_longer_lists_the_email(self):
        with _db() as db:
            owner = SupplierMaster(supplier_name="OLD OWNER"); db.add(owner); db.commit()
            db.add(SupplierEmail(supplier_id=owner.id, supplier_name=owner.supplier_name,
                                 to_emails=["someone@else.test"], is_active=True))
            s = SupplierMaster(supplier_name="SHIVAM ENGINEERS"); db.add(s); db.commit()
            _supplier_login(db, supplier_id=owner.id, company_id=_company_id(db, "102"))
            with use_company("public"):
                summary = svc.sync_supplier_logins(
                    db, supplier_id=s.id, supplier_name="SHIVAM ENGINEERS", to_emails=[EMAIL])
            self.assertEqual(summary["relinked"], [EMAIL])

    def test_genuine_conflict_names_the_owner(self):
        with _db() as db:
            owner = SupplierMaster(supplier_name="GANESH TOOLS"); db.add(owner); db.commit()
            db.add(SupplierEmail(supplier_id=owner.id, supplier_name=owner.supplier_name,
                                 to_emails=[EMAIL.upper()], is_active=True))
            s = SupplierMaster(supplier_name="SHIVAM ENGINEERS"); db.add(s); db.commit()
            login = _supplier_login(db, supplier_id=owner.id, company_id=_company_id(db, "102"))
            with use_company("public"):
                summary = svc.sync_supplier_logins(
                    db, supplier_id=s.id, supplier_name="SHIVAM ENGINEERS", to_emails=[EMAIL])
            self.assertEqual(summary["created"], [])
            self.assertEqual(len(summary["conflicts"]), 1)
            reason = summary["conflicts"][0]["reason"]
            self.assertIn("GANESH TOOLS", reason)
            self.assertIn(str(owner.id), reason)
            db.refresh(login)
            self.assertEqual(login.supplier_id, owner.id)

    def test_staff_account_still_conflicts(self):
        with _db() as db:
            user_service.create_user(db, email=EMAIL, password="secret123",
                                     full_name="Desk Admin", role="admin")
            s = SupplierMaster(supplier_name="SHIVAM ENGINEERS"); db.add(s); db.commit()
            with use_company("company_101"):
                summary = svc.sync_supplier_logins(
                    db, supplier_id=s.id, supplier_name="SHIVAM ENGINEERS", to_emails=[EMAIL])
            self.assertEqual(summary["created"], [])
            self.assertIn("staff account", summary["conflicts"][0]["reason"])


class LoginPicksCompanyTests(unittest.TestCase):
    def test_authenticate_prefers_the_company_chosen_at_login(self):
        with _db() as db:
            a = user_service.create_user(
                db, email=EMAIL, password="pw-for-101", role=Role.SUPPLIER, supplier_id=916,
                company_id=_company_id(db, "101"), check_email=False)
            b = user_service.create_user(
                db, email=EMAIL, password="pw-for-102", role=Role.SUPPLIER, supplier_id=57,
                company_id=_company_id(db, "102"), check_email=False)
            self.assertEqual(user_service.authenticate(db, EMAIL, "pw-for-101", "101").id, a.id)
            self.assertEqual(user_service.authenticate(db, EMAIL, "pw-for-102", "102").id, b.id)
            # Wrong company picked, but the password identifies the account.
            self.assertEqual(user_service.authenticate(db, EMAIL, "pw-for-102", "101").id, b.id)
            self.assertIsNone(user_service.authenticate(db, EMAIL, "nope", "101"))


class EmailMasterApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
        )
        Base.metadata.create_all(bind=self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)()
        company_service.seed_companies(self.db)
        main_mod.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(main_mod.app)
        self.patch = patch.object(svc, "send_credentials_email", return_value=False)
        self.patch.start()
        user_service.create_user(self.db, email="admin@x.com", password="secret123", role="admin")
        r = self.client.post("/api/auth/login", json={"email": "admin@x.com", "password": "secret123"})
        self.h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    def tearDown(self):
        self.patch.stop()
        main_mod.app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_edit_mapping_of_inactive_supplier_saves(self):
        s = SupplierMaster(supplier_name="SHIVAM ENGINEERS"); self.db.add(s); self.db.commit()
        created = self.client.post("/api/supplier-emails", headers=self.h, json={
            "supplier_id": s.id, "to_emails": [EMAIL]})
        self.assertEqual(created.status_code, 201, created.text)
        s.is_active = False
        self.db.commit()
        r = self.client.put(f"/api/supplier-emails/{created.json()['id']}", headers=self.h, json={
            "supplier_id": s.id, "to_emails": [EMAIL],
            "cc_emails": ["followuphconnect2012@gmail.com"]})
        self.assertEqual(r.status_code, 200, r.text)
        listed = self.client.get("/api/supplier-emails", headers=self.h).json()
        self.assertEqual(listed[0]["cc_emails"], ["followuphconnect2012@gmail.com"])

    def test_logins_list_is_company_scoped(self):
        s = SupplierMaster(supplier_name="ACME"); self.db.add(s); self.db.commit()
        _supplier_login(self.db, supplier_id=s.id, company_id=_company_id(self.db, "101"),
                        email="other@co101.test")
        mine = _supplier_login(self.db, supplier_id=s.id, company_id=_company_id(self.db, "102"),
                               email="mine@co102.test")
        r = self.client.get(f"/api/supplier-accounts?supplier_id={s.id}", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([u["email"] for u in r.json()], ["mine@co102.test"])
        # Another company's login cannot be reset from here.
        foreign = self.db.query(User).filter_by(email="other@co101.test").one()
        self.assertEqual(
            self.client.post(f"/api/supplier-accounts/{foreign.id}/reset-password",
                             headers=self.h).status_code, 404)
        self.assertEqual(
            self.client.post(f"/api/supplier-accounts/{mine.id}/deactivate",
                             headers=self.h).status_code, 200)


if __name__ == "__main__":
    unittest.main()
