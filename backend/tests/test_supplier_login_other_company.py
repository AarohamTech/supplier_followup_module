"""Supplier portal logins for a non-default company.

Regression (2026-10-17): `users` lives in `public` (shared by every company),
but `users.supplier_id` carried a foreign key to `public.supplier_master`.
Company 101's suppliers live in `company_101.supplier_master`, so creating a
login for one (SHIVAM ENGINEERS id 916, G S INFO 825, HINDUSTAN 1173) hit an FK
violation: the Email Master save 500'd, no login was created and no password
mail was ever queued. A supplier_id only means something inside the company
the account is pinned to (`users.company_id`), so it cannot be a DB-level FK.
"""
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_supplier_login_101.sqlite")

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import supplier_account_service  # noqa: E402


@contextmanager
def _fk_enforcing_db():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class SupplierLoginOtherCompanyTests(unittest.TestCase):
    def test_users_supplier_id_is_not_a_db_foreign_key(self):
        self.assertEqual(set(User.__table__.c.supplier_id.foreign_keys), set())

    def test_login_is_created_and_mailed_for_a_supplier_only_known_to_another_company(self):
        with _fk_enforcing_db() as db:
            # Supplier 916 exists only in company_101's own supplier_master —
            # there is no such row in the shared (public) schema.
            with patch.object(supplier_account_service, "send_credentials_email",
                              return_value=True) as send:
                summary = supplier_account_service.sync_supplier_logins(
                    db, supplier_id=916, supplier_name="SHIVAM ENGINEERS",
                    to_emails=["shivam.engineers@rediffmail.com"],
                )

            self.assertEqual([c["email"] for c in summary["created"]],
                             ["shivam.engineers@rediffmail.com"])
            self.assertEqual(summary["emailed"], ["shivam.engineers@rediffmail.com"])
            send.assert_called_once()
            login = db.query(User).filter_by(email="shivam.engineers@rediffmail.com").one()
            self.assertEqual(login.supplier_id, 916)


if __name__ == "__main__":
    unittest.main()
