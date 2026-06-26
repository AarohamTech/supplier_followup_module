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
from app.models import Asn, CommunicationMessage, Notification, ProcurementRecord, SupplierMaster, User  # noqa: E402,F401
from app.services import ai_tools_service, asn_service, notification_service, supplier_account_service, user_service  # noqa: E402


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


class NotificationTests(unittest.TestCase):
    def test_staff_and_supplier_fanout_and_read(self):
        with _temp_db() as db:
            s = _supplier(db)
            staff = user_service.create_user(db, email="staff@corp.com", password="x" * 8, role=Role.MANAGER)
            sup_user = user_service.create_user(
                db, email="a@s.com", password="x" * 8, role=Role.SUPPLIER, supplier_id=s.id)

            # Staff fan-out.
            n = notification_service.notify_staff(
                db, type="SUPPLIER_MESSAGE", title="hi", supplier_id=s.id, supplier_po_no="PO-1")
            self.assertEqual(n, 1)
            self.assertEqual(notification_service.unread_count(db, staff.id), 1)
            self.assertEqual(notification_service.unread_count(db, sup_user.id), 0)

            # Supplier fan-out — passes supplier_id both as audience AND context
            # column (regression: must not collide).
            n2 = notification_service.notify_supplier(
                db, s.id, type="STAFF_REPLY", title="reply", supplier_id=s.id, supplier_po_no="PO-1")
            self.assertEqual(n2, 1)
            self.assertEqual(notification_service.unread_count(db, sup_user.id), 1)

            # Read flow.
            notif = notification_service.list_for_user(db, sup_user.id)[0]
            self.assertTrue(notification_service.mark_read(db, sup_user.id, notif.id))
            self.assertEqual(notification_service.unread_count(db, sup_user.id), 0)
            # A user can't mark someone else's notification.
            self.assertFalse(notification_service.mark_read(db, staff.id, notif.id + 999))


class AiToolScopeTests(unittest.TestCase):
    """A supplier's assistant tools must never reach another supplier's data."""

    def _seed_two_suppliers(self, db):
        for name, po, sid in [("ACME TOOLS", "ACME-1", 1), ("BETA PARTS", "BETA-1", 2)]:
            db.add(SupplierMaster(supplier_name=name, is_active=True))
            db.add(ProcurementRecord(
                crm_no=f"CRM-{po}", material_name="Widget", supplier_po_no=po,
                supplier_name=name, signal="BLACK"))
            db.add(CommunicationMessage(
                direction="INCOMING", status="RECEIVED", channel="EMAIL",
                supplier_id=sid, supplier_name=name, supplier_po_no=po,
                subject="hi", body="secret note"))
        db.commit()

    def test_supplier_scope_cannot_see_other_supplier(self):
        with _temp_db() as db:
            self._seed_two_suppliers(db)
            acme = ai_tools_service.ToolScope(supplier_id=1, supplier_name="ACME TOOLS")
            run = ai_tools_service.make_executor(db, acme)

            # Overview is scoped to ACME's single record; no customer-inbox leak.
            ov = run("get_overview", {})
            self.assertEqual(ov["total_records"], 1)
            self.assertNotIn("open_customer_mails", ov)

            # Cannot read BETA's PO or its thread.
            self.assertFalse(run("get_po_status", {"supplier_po_no": "BETA-1"})["found"])
            self.assertTrue(run("get_po_status", {"supplier_po_no": "ACME-1"})["found"])
            self.assertEqual(run("get_mail_thread", {"supplier_po_no": "BETA-1"})["message_count"], 0)
            self.assertEqual(run("get_mail_thread", {"supplier_po_no": "ACME-1"})["message_count"], 1)

            # list_red_pos ignores a spoofed supplier_name arg and stays on ACME.
            red = run("list_red_pos", {"supplier_name": "BETA PARTS"})
            pos = {p["supplier_po_no"] for p in red["purchase_orders"]}
            self.assertNotIn("BETA-1", pos)

            # Staff-only tools are refused for suppliers.
            self.assertEqual(run("search_supplier", {"query": "BETA"}).get("error"), "not available")
            self.assertEqual(run("search_knowledge", {"query": "x"}).get("error"), "not available")

            # Staff scope (default) CAN see BETA's PO.
            staff = ai_tools_service.make_executor(db)
            self.assertTrue(staff("get_po_status", {"supplier_po_no": "BETA-1"})["found"])


if __name__ == "__main__":
    unittest.main()
