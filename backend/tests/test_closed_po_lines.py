"""Closed PO lines must drop out everywhere — one definition (po_open_lines).

Client 2026-11-12: admin pages showed closed POs, counts differed between the
dashboard / Orders / follow-up pages, and the evening auto follow-up cycle was
about to mail suppliers about POs that were already closed. My Orders (employee
portal) was right. These tests pin the shared predicate and every caller that
used to disagree: the follow-up group builder, the auto queue, the admin Orders
list, the dashboard, the employee My Orders, and the send worker's last-moment
re-check of already-queued mail.
"""
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ProcurementRecord
from app.models.communication_message import CommunicationMessage
from app.models.mail_history import MailHistory
from app.models.supplier import SupplierMaster
from app.models.supplier_email import SupplierEmail
from app.routers import employee_portal
from app.routers import procurement as procurement_router
from app.services import po_followup_mail_service as pfm
from app.services import po_followup_service as pfs
from app.services import po_open_lines as pol
from app.services import po_view_service as pv
from app.services import user_service

SUP = "ACME TOOLS"
DELISTED_AT = datetime(2026, 11, 10)


@contextmanager
def _temp_db():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db, Session
    finally:
        db.close()
        engine.dispose()


def _line(db, *, crm, po, signal="BLACK", owner="E1", **kw):
    r = ProcurementRecord(
        crm_no=crm, material_name=f"M-{crm}", supplier_po_no=po, supplier_name=SUP,
        po_status=kw.pop("po_status", "APPROVED"), signal=signal, owner_emp_code=owner, **kw,
    )
    db.add(r)
    db.commit()
    return r


def _seed_mixed(db):
    """PO-OPEN: one open GREEN line + closed BLACK lines (each closed reason).
    PO-DONE: every line closed. Returns nothing — tests query by PO."""
    _line(db, crm="O1", po="PO-OPEN", signal="GREEN")
    _line(db, crm="O2", po="PO-OPEN", delisted_at=DELISTED_AT)
    _line(db, crm="O3", po="PO-OPEN", receipt_status="COMPLETED")
    _line(db, crm="O4", po="PO-OPEN", cancellation_status="CANCELLED")
    _line(db, crm="O5", po="PO-OPEN", po_status="CLOSED")
    _line(db, crm="D1", po="PO-DONE", delisted_at=DELISTED_AT)
    _line(db, crm="D2", po="PO-DONE", receipt_status="COMPLETED")
    _line(db, crm="D3", po="PO-DONE", cancellation_status="CANCELLED")


def _map_supplier(db):
    sup = SupplierMaster(supplier_name=SUP, is_active=True)
    db.add(sup)
    db.flush()
    db.add(SupplierEmail(supplier_id=sup.id, supplier_name=SUP, to_emails=["s@acme.com"],
                         cc_emails=[], bcc_emails=[], escalation_emails=[], is_active=True))
    db.commit()


class PredicateTests(unittest.TestCase):
    def test_closed_reasons(self):
        R = ProcurementRecord
        self.assertIsNone(pol.closed_reason(R()))
        self.assertIsNone(pol.closed_reason(R(receipt_status="PARTIAL", po_status="DISPATCHED")))
        self.assertIsNotNone(pol.closed_reason(R(delisted_at=DELISTED_AT)))
        self.assertIsNotNone(pol.closed_reason(R(receipt_status="completed")))
        self.assertIsNotNone(pol.closed_reason(R(cancellation_status="CANCELLED")))
        self.assertIsNotNone(pol.closed_reason(R(po_status=" closed ")))
        # Pending cancel: still open (shown), but never chased.
        pending = R(cancellation_status="PENDING")
        self.assertTrue(pol.is_open_line(pending))
        self.assertFalse(pol.is_chaseable_line(pending))

    def test_sql_clauses_match_python(self):
        with _temp_db() as (db, _):
            _seed_mixed(db)
            _line(db, crm="P1", po="PO-PEND", cancellation_status="PENDING")
            rows = db.scalars(select(ProcurementRecord)).all()
            sql_open = {r.id for r in db.scalars(
                select(ProcurementRecord).where(pol.open_line_clause())).all()}
            sql_chase = {r.id for r in db.scalars(
                select(ProcurementRecord).where(pol.chaseable_line_clause())).all()}
            self.assertEqual(sql_open, {r.id for r in rows if pol.is_open_line(r)})
            self.assertEqual(sql_chase, {r.id for r in rows if pol.is_chaseable_line(r)})
            self.assertEqual(len(sql_open), 2)   # O1 + P1
            self.assertEqual(len(sql_chase), 1)  # O1


class GroupBuilderTests(unittest.TestCase):
    def test_build_all_po_groups_drops_closed_lines_and_closed_pos(self):
        with _temp_db() as (db, _):
            _seed_mixed(db)
            groups = {g["supplier_po_no"]: g for g in pfs.build_all_po_groups(db)}
            self.assertEqual(set(groups), {"PO-OPEN"})
            g = groups["PO-OPEN"]
            self.assertEqual(g["material_count"], 1)
            # A closed BLACK line must not make the PO BLACK.
            self.assertEqual(g["overall_signal"], "GREEN")
            self.assertEqual(pfs.build_all_po_groups(db, signal="BLACK"), [])
            # "Show closed" still reaches everything.
            every = {g["supplier_po_no"] for g in pfs.build_all_po_groups(db, include_closed=True)}
            self.assertEqual(every, {"PO-OPEN", "PO-DONE"})
            self.assertIsNone(pfs.get_po_group(db, SUP, "PO-DONE"))


class AutoQueueTests(unittest.TestCase):
    def test_queue_never_mails_closed_pos_and_lists_only_open_lines(self):
        with _temp_db() as (db, _):
            _map_supplier(db)
            _seed_mixed(db)
            with patch.object(pfm.settings, "AUTO_PO_FOLLOWUP_ENABLED", True, create=True), \
                 patch.object(pfm, "_send_realtime_now", return_value=0):
                out = pfm.queue_due_po_followups(db)
            pos = {r.get("supplier_po_no") for r in out["results"]}
            self.assertNotIn("PO-DONE", pos)
            created = [r for r in out["results"] if r.get("created")]
            self.assertEqual([r["supplier_po_no"] for r in created], ["PO-OPEN"])
            self.assertEqual(created[0]["material_count"], 1)
            self.assertEqual(created[0]["overall_signal"], "GREEN")
            # Only the open line was flagged READY; closed lines untouched.
            ready = {r.crm_no for r in db.scalars(select(ProcurementRecord)).all()
                     if r.mail_status == "READY"}
            self.assertEqual(ready, {"O1"})

    def test_manual_send_for_closed_po_is_skipped_with_reason(self):
        with _temp_db() as (db, _):
            _map_supplier(db)
            _seed_mixed(db)
            res = pfm.create_po_followup_mail(db, supplier_name=SUP, supplier_po_no="PO-DONE")
            self.assertFalse(res.created)
            self.assertEqual(res.skipped_reason, pfm.PO_CLOSED_SKIP)


class AdminAndEmployeeViewTests(unittest.TestCase):
    def test_admin_orders_list_hides_closed_unless_asked(self):
        with _temp_db() as (db, _):
            _seed_mixed(db)
            lines, total = pv.material_lines(db)
            self.assertEqual((total, [l["crm_no"] for l in lines]), (1, ["O1"]))
            lines, total = pv.material_lines(db, include_closed=True)
            self.assertEqual(total, 8)
            self.assertEqual({l["crm_no"] for l in lines if l["closed"]},
                             {"O2", "O3", "O4", "O5", "D1", "D2", "D3"})
            groups, gtotal = pv.grouped_pos(db)
            self.assertEqual((gtotal, [g["supplier_po_no"] for g in groups]), (1, ["PO-OPEN"]))
            self.assertEqual(groups[0]["material_count"], 1)
            # The staff PO Follow-ups list (/api/procurement) agrees.
            out = procurement_router.list_records(
                db=db, signal=None, supplier_name=None, po_no=None, supplier_po_no=None,
                crm_no=None, po_status=None, owner_emp_code=None, shipment_date_from=None,
                shipment_date_to=None, search=None, include_closed=False, page=1, size=50,
            )
            self.assertEqual(out.total, 1)

    def test_dashboard_counts_only_open_lines(self):
        with _temp_db() as (db, _):
            _seed_mixed(db)
            kpis = procurement_router.dashboard(db=db, owner_emp_code=None)
            self.assertEqual(kpis.total_records, 1)
            self.assertEqual(kpis.black_count, 0)
            self.assertEqual(kpis.green_count, 1)

    def test_employee_my_orders_and_dashboard_hide_closed(self):
        with _temp_db() as (db, _):
            _seed_mixed(db)
            emp = user_service.create_user(
                db, email="e1@employee.local", password="pw", full_name="Owner",
                role="employee", emp_code="E1", username="DESK1",
            )
            out = employee_portal.list_orders(user=emp, db=db)
            self.assertEqual((out["total"], [i["crm_no"] for i in out["items"]]), (1, ["O1"]))
            kpis = employee_portal.procurement_dashboard(user=emp, db=db)
            self.assertEqual(kpis.total_records, 1)
            summary = employee_portal.summary(user=emp, db=db)
            self.assertEqual((summary.total_pos, summary.black), (1, 0))


class SendWorkerRecheckTests(unittest.TestCase):
    def _queue(self, db, po, mail_type="PO_FOLLOWUP_BLACK"):
        anchor = db.scalar(select(ProcurementRecord.id).where(ProcurementRecord.supplier_po_no == po))
        hist = MailHistory(procurement_record_id=anchor,
                           supplier_name=SUP, supplier_po_no=po, subject="s", body="b",
                           mail_type=mail_type, sent_status="READY",
                           material_name="ALL MATERIALS (1)", to_emails=["s@acme.com"])
        db.add(hist)
        db.flush()
        msg = CommunicationMessage(
            direction="OUTGOING", status="READY", channel="EMAIL", mail_type=mail_type,
            supplier_name=SUP, supplier_po_no=po, subject="s", body="b",
            to_emails=["s@acme.com"], raw_payload={"mail_history_id": hist.id},
        )
        db.add(msg)
        db.commit()
        return msg, hist

    def test_queued_followup_for_now_closed_po_is_skipped_not_sent(self):
        from app.workers import mail_send_worker as w

        with _temp_db() as (db, Session):
            line = _line(db, crm="X1", po="PO-X", mail_status="READY")
            msg, hist = self._queue(db, "PO-X")
            # The CRM closes the PO while the mail waits for the night window.
            line.delisted_at = DELISTED_AT
            db.commit()
            msg_id, hist_id, line_id = msg.id, hist.id, line.id

            client = MagicMock()
            cfg = MagicMock(from_addr="noreply@x.com")
            with patch.object(w, "SessionLocal", Session), \
                 patch.object(w.mail_config_service, "get_smtp_config", return_value=cfg), \
                 patch.object(w, "_open_client", return_value=client):
                results = w._send_bucket([msg_id], "public")

            self.assertEqual(results[0]["status"], "SKIPPED")
            client.send_message.assert_not_called()
            check = Session()
            m = check.get(CommunicationMessage, msg_id)
            self.assertEqual(m.status, "SKIPPED")
            self.assertIn("PO closed", m.error_message)  # shown in the Mail Log
            self.assertEqual(check.get(MailHistory, hist_id).sent_status, "SKIPPED")
            self.assertEqual(check.get(ProcurementRecord, line_id).mail_status, "SKIPPED")
            check.close()

    def test_open_po_and_non_followup_mail_are_not_skipped(self):
        from app.workers import mail_send_worker as w

        with _temp_db() as (db, _):
            _line(db, crm="Y1", po="PO-Y")
            _line(db, crm="Y2", po="PO-Y", delisted_at=DELISTED_AT)
            open_msg, _ = self._queue(db, "PO-Y")
            self.assertIsNone(w.closed_po_skip_reason(db, open_msg))
            _line(db, crm="Z1", po="PO-Z", delisted_at=DELISTED_AT)
            staff = CommunicationMessage(direction="OUTGOING", status="READY", channel="EMAIL",
                                         mail_type=None, supplier_name=SUP, supplier_po_no="PO-Z")
            db.add(staff)
            db.commit()
            self.assertIsNone(w.closed_po_skip_reason(db, staff))

    def test_send_message_now_skips_closed_po(self):
        from app.workers import mail_send_worker as w

        with _temp_db() as (db, _):
            _line(db, crm="G1", po="PO-G", receipt_status="COMPLETED")
            msg, _ = self._queue(db, "PO-G", mail_type="PO_FOLLOWUP_GREEN")
            cfg = MagicMock()
            cfg.ready.return_value = (True, "")
            with patch.object(w.mail_config_service, "get_smtp_config", return_value=cfg), \
                 patch.object(w, "_send_one") as send_one:
                out = w.send_message_now(db, msg.id)
            send_one.assert_not_called()
            self.assertEqual(out["status"], "SKIPPED")


if __name__ == "__main__":
    unittest.main()
