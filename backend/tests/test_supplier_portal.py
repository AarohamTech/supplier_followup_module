"""Tests for supplier portal additions: roles, ASN lifecycle, login provisioning.

DB-backed with an in-memory SQLite (production data untouched).
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager

# Force a throwaway SQLite DB before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_supplier_portal.sqlite")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.roles import Role, normalize_role, rank, role_at_least, is_valid_role  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import Asn, ProcurementRecord, SupplierMaster, User  # noqa: E402,F401
from app.services import asn_service, supplier_account_service, user_service  # noqa: E402


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


def _supplier(db, name="M/S SUPERB TOOLS") -> SupplierMaster:
    s = SupplierMaster(supplier_name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class RoleTests(unittest.TestCase):
    def test_supplier_is_known_but_outranked_by_staff(self):
        self.assertTrue(is_valid_role(Role.SUPPLIER))
        self.assertEqual(normalize_role("supplier"), Role.SUPPLIER)
        self.assertEqual(rank(Role.SUPPLIER), 0)
        # A supplier never satisfies any staff guard.
        self.assertFalse(role_at_least(Role.SUPPLIER, Role.VIEWER))
        self.assertFalse(role_at_least(Role.SUPPLIER, Role.ADMIN))
        # Unknown still falls back to the default staff role.
        self.assertEqual(normalize_role("nonsense"), Role.VIEWER)


class AsnLifecycleTests(unittest.TestCase):
    def test_create_draft_then_advance_to_delivered(self):
        with _temp_db() as db:
            s = _supplier(db)
            asn = asn_service.create_asn(
                db, supplier_id=s.id, supplier_name=s.supplier_name,
                supplier_po_no="SBT-1", submit=False,
                items=[{"material_name": "Drill", "qty_shipped": 5}],
            )
            self.assertEqual(asn.status, "DRAFT")
            self.assertEqual(asn.progress_percent, 0)
            self.assertTrue(asn.asn_no.startswith("ASN-"))
            self.assertEqual(len(asn.items), 1)

            asn_service.add_event(db, asn, stage="IN_TRANSIT")
            self.assertEqual(asn.status, "IN_TRANSIT")
            self.assertEqual(asn.progress_percent, 55)

            asn_service.add_event(db, asn, stage="DELIVERED")
            self.assertEqual(asn.status, "DELIVERED")
            self.assertEqual(asn.progress_percent, 100)
            self.assertIsNotNone(asn.delivered_at)
            self.assertEqual(len(asn.events), 2)

    def test_summary_buckets_and_completion(self):
        with _temp_db() as db:
            s = _supplier(db)
            # active (in transit)
            asn_service.create_asn(db, supplier_id=s.id, supplier_name=s.supplier_name,
                                   supplier_po_no="PO-A", submit=True)
            a2 = asn_service.create_asn(db, supplier_id=s.id, supplier_name=s.supplier_name,
                                        supplier_po_no="PO-A", submit=True)
            asn_service.add_event(db, a2, stage="AT_CUSTOMS")  # pending bucket
            a3 = asn_service.create_asn(db, supplier_id=s.id, supplier_name=s.supplier_name,
                                        supplier_po_no="PO-B", submit=True)
            asn_service.add_event(db, a3, stage="IN_TRANSIT", alert=True, alert_reason="Delayed")  # urgent
            a4 = asn_service.create_asn(db, supplier_id=s.id, supplier_name=s.supplier_name,
                                        supplier_po_no="PO-C", submit=True)
            asn_service.add_event(db, a4, stage="DELIVERED")  # finalized + completes PO-C

            summary = asn_service.asn_summary(db, supplier_id=s.id)
            self.assertEqual(summary["pending"], 1)
            self.assertEqual(summary["urgent"], 1)
            self.assertEqual(summary["finalized"], 1)
            self.assertGreaterEqual(summary["active"], 1)

            completed = asn_service.completed_po_numbers(db, supplier_id=s.id)
            self.assertEqual(completed, {"PO-C"})


class ProvisioningTests(unittest.TestCase):
    def test_sync_creates_deactivates_and_flags_conflicts(self):
        with _temp_db() as db:
            s = _supplier(db)
            # Pre-existing staff account that must not be hijacked.
            user_service.create_user(db, email="staff@corp.com", password="x" * 8,
                                     role=Role.ADMIN)

            res = supplier_account_service.sync_supplier_logins(
                db, supplier_id=s.id, supplier_name=s.supplier_name,
                to_emails=["a@s.com", "b@s.com", "staff@corp.com"], send_email=False,
            )
            self.assertEqual({c["email"] for c in res["created"]}, {"a@s.com", "b@s.com"})
            self.assertEqual([c["email"] for c in res["conflicts"]], ["staff@corp.com"])

            a = user_service.get_by_email(db, "a@s.com")
            self.assertEqual(a.role, Role.SUPPLIER)
            self.assertEqual(a.supplier_id, s.id)
            self.assertTrue(a.must_change_password)
            self.assertTrue(a.is_active)

            # Drop b@s.com from the mapping → its login is deactivated, not deleted.
            res2 = supplier_account_service.sync_supplier_logins(
                db, supplier_id=s.id, supplier_name=s.supplier_name,
                to_emails=["a@s.com"], send_email=False,
            )
            self.assertIn("b@s.com", res2["deactivated"])
            b = user_service.get_by_email(db, "b@s.com")
            self.assertIsNotNone(b)
            self.assertFalse(b.is_active)

    def test_admin_reset_sets_temp_and_force_change(self):
        with _temp_db() as db:
            s = _supplier(db)
            supplier_account_service.sync_supplier_logins(
                db, supplier_id=s.id, supplier_name=s.supplier_name,
                to_emails=["a@s.com"], send_email=False,
            )
            user = user_service.get_by_email(db, "a@s.com")
            # Simulate the supplier having changed their password (flag cleared).
            user_service.set_password(db, user, "Chosen!123", must_change=False)
            self.assertFalse(user.must_change_password)

            result = supplier_account_service.reset_supplier_login_password(
                db, user, send_email=False
            )
            self.assertTrue(result["temp_password"])
            db.refresh(user)
            self.assertTrue(user.must_change_password)


if __name__ == "__main__":
    unittest.main()
