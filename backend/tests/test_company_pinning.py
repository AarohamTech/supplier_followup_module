"""Portal-account company pinning: logins provisioned while switched into a company
are pinned to it (company_id), and the Employee Logins list is company-scoped."""
import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.tenant import use_company
from app.database import Base
from app.models import User
from app.services import company_service, employee_account_service as emp_svc


@contextmanager
def _temp_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        company_service.seed_companies(db)
        yield db
    finally:
        db.close()
        engine.dispose()


def _company_id(db, code: str) -> int:
    return company_service.get_by_code(db, code).id


class PinningTests(unittest.TestCase):
    def test_provision_under_101_pins_company(self):
        with _temp_db() as db:
            with use_company("company_101"):
                out = emp_svc.provision_from_rows(db, [
                    {"EMPLOYEE_ID": "1110000001", "EMPLOYEE_LOGIN_ID": "ENT_USER1",
                     "FIRST_NAME": "Ent", "LAST_NAME": "User"},
                ])
            self.assertEqual(len(out["created"]), 1)
            user = db.query(User).filter(User.username == "ENT_USER1").one()
            self.assertEqual(user.company_id, _company_id(db, "101"))

    def test_provision_under_default_pins_102(self):
        with _temp_db() as db:
            with use_company("public"):
                emp_svc.provision_from_rows(db, [
                    {"EMPLOYEE_ID": "1010000001", "EMPLOYEE_LOGIN_ID": "TECH_USER1"},
                ])
            user = db.query(User).filter(User.username == "TECH_USER1").one()
            self.assertEqual(user.company_id, _company_id(db, "102"))

    def test_create_one_pins_current_company(self):
        with _temp_db() as db:
            with use_company("company_101"):
                emp_svc.create_employee(db, username="ENT_SINGLE", full_name=None, emp_code="E9")
            user = db.query(User).filter(User.username == "ENT_SINGLE").one()
            self.assertEqual(user.company_id, _company_id(db, "101"))

    def test_login_resolution_pins_portal_account_to_its_company(self):
        with _temp_db() as db:
            with use_company("company_101"):
                emp_svc.provision_from_rows(db, [
                    {"EMPLOYEE_ID": "1110000002", "EMPLOYEE_LOGIN_ID": "ENT_USER2"},
                ])
            user = db.query(User).filter(User.username == "ENT_USER2").one()
            # Even if the login requests 102, a pinned portal account resolves to 101.
            company = company_service.resolve_login_company(db, user, "102")
            self.assertEqual(company.code, "101")

    def test_list_is_company_scoped_with_legacy_null_on_default(self):
        with _temp_db() as db:
            # legacy Tech login (company_id NULL) + a pinned Enterprises login
            db.add(User(email="legacy@e.local", hashed_password="x", role="employee",
                        emp_code="L1", username="LEGACY1"))
            db.commit()
            with use_company("company_101"):
                emp_svc.provision_from_rows(db, [
                    {"EMPLOYEE_ID": "1110000003", "EMPLOYEE_LOGIN_ID": "ENT_USER3"},
                ])
            with use_company("public"):
                names_102 = {u.username for u in emp_svc.list_employee_logins(db)}
            with use_company("company_101"):
                names_101 = {u.username for u in emp_svc.list_employee_logins(db)}
            self.assertIn("LEGACY1", names_102)       # NULL shows under default
            self.assertNotIn("ENT_USER3", names_102)
            self.assertEqual(names_101, {"ENT_USER3"})


if __name__ == "__main__":
    unittest.main()
