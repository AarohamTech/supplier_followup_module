"""Employee logins promoted to a staff role become staff accounts; the mail
keyword scan no longer overwrites CRM status; auto-ack drafts are off."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.core.account_kind import is_employee_account, is_staff_account, is_supplier_account
from app.scheduler import jobs
from app.services import status_change_service


def U(**kw):
    base = {"supplier_id": None, "emp_code": None, "role": "user"}
    base.update(kw)
    return SimpleNamespace(**base)


class AccountKindTests(unittest.TestCase):
    def test_plain_staff(self):
        u = U(role="admin")
        self.assertTrue(is_staff_account(u))
        self.assertFalse(is_employee_account(u))

    def test_employee_login(self):
        u = U(emp_code="E12", role="employee")
        self.assertTrue(is_employee_account(u))
        self.assertFalse(is_staff_account(u))

    def test_employee_promoted_to_admin_is_staff(self):
        for role in ("viewer", "user", "manager", "admin"):
            u = U(emp_code="E12", role=role)
            self.assertTrue(is_staff_account(u), role)
            self.assertFalse(is_employee_account(u), role)

    def test_supplier_is_never_staff_or_employee(self):
        u = U(supplier_id=5, role="admin", emp_code="E1")
        self.assertTrue(is_supplier_account(u))
        self.assertFalse(is_staff_account(u))
        self.assertFalse(is_employee_account(u))


class _FakeDb:
    def __init__(self):
        self.added = []

    def add(self, x):
        self.added.append(x)

    def commit(self):
        pass

    def refresh(self, x):
        pass


class MailStatusOverwriteTests(unittest.TestCase):
    def test_keyword_status_and_qty_do_not_overwrite_crm(self):
        rec = SimpleNamespace(id=1, po_status="OPEN", shipment_date=None, qty=10.0,
                              last_supplier_reply=None)
        db = _FakeDb()
        out = status_change_service.apply_parsed_reply(
            db, rec, None, {"status": "ready", "quantity": 3.0}
        )
        self.assertIsNone(out)
        self.assertEqual(rec.po_status, "OPEN")
        self.assertEqual(rec.qty, 10.0)

    def test_auto_ack_runner_is_off(self):
        out = jobs.auto_reply_runner()
        self.assertTrue(out.get("skipped"))


if __name__ == "__main__":
    unittest.main()
