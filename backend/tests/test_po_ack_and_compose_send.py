"""PO acknowledgement (signed link + portal) and the compose send path.

Compose: a manual mail is sent in the request (never held by the off-hours
auto follow-up window), recipient entries holding several addresses are split
instead of collapsing to an empty recipient, and a failed immediate send is
reported to the sender.

PO ack: tokens are signed and tamper-proof, acknowledging is idempotent, the
first ack notifies the people responsible and posts into the PO's hub thread,
and follow-up mails carry the link only while the PO is unacknowledged.
"""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    CommunicationMessage,
    Notification,
    PoAcknowledgement,
    ProcurementRecord,
    SupplierAssignment,
    SupplierMaster,
    User,
)
from app.services import compose_service, po_ack_service
from app.services.mail_config_service import SmtpConfig
from app.workers import mail_send_worker

READY_CFG = SmtpConfig(
    enabled=True, host="smtp.example.com", port=587, user="", password="",
    from_addr="sales@example.com",
)
IST_2300 = datetime(2026, 8, 26, 17, 30)  # inside the 19:00-08:00 hold window


@contextmanager
def _session():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_po(db) -> dict:
    supplier = SupplierMaster(supplier_name="Vedant Tools Pvt Ltd")
    db.add(supplier)
    db.flush()
    owner = User(email="owner@hariom.in", hashed_password="x", role="user",
                 is_active=True, emp_code="E100", username="owner")
    assigned = User(email="buyer@hariom.in", hashed_password="x", role="user",
                    is_active=True, username="buyer")
    bystander = User(email="other@hariom.in", hashed_password="x", role="user",
                     is_active=True, username="other")
    db.add_all([owner, assigned, bystander])
    db.flush()
    db.add(SupplierAssignment(supplier_id=supplier.id, user_id=assigned.id))
    recs = [
        ProcurementRecord(crm_no="C1", material_name="Bolt M8", supplier_name="Vedant Tools Pvt Ltd",
                          supplier_po_no="000449", po_short_ref="2627-001703", owner_emp_code="E100"),
        ProcurementRecord(crm_no="C2", material_name="Nut M8", supplier_name="Vedant Tools Pvt Ltd",
                          supplier_po_no="000450", po_short_ref="2627-001703", owner_emp_code="E100"),
        # Same recycled counter, different supplier — must stay separate.
        ProcurementRecord(crm_no="C3", material_name="Washer", supplier_name="Other Supplier",
                          supplier_po_no="000449", po_short_ref="2627-009999"),
    ]
    db.add_all(recs)
    db.commit()
    return {"supplier": supplier, "owner": owner, "assigned": assigned,
            "bystander": bystander, "recs": recs}


# ── compose ──────────────────────────────────────────────────────────────────
class ComposeSendPathTests(unittest.TestCase):
    def test_compose_sends_immediately_even_inside_the_hold_window(self):
        sent: list = []
        with _session() as db, \
                patch.object(mail_send_worker.mail_config_service, "get_smtp_config",
                             return_value=READY_CFG), \
                patch.object(mail_send_worker, "_send_one",
                             side_effect=lambda em, cfg=None: sent.append(em)):
            out = compose_service.compose_and_send(
                db, to_emails=["vendor@example.com"], subject="Status", body="Hello",
            )
            msg = db.get(CommunicationMessage, out["message_id"])
            self.assertTrue(out["sent"])
            self.assertEqual(msg.status, "SENT")
            self.assertEqual(len(sent), 1)
        # HUB_COMPOSE is not an auto follow-up → never held by the window.
        self.assertFalse(mail_send_worker.is_held_mail_type("HUB_COMPOSE"))

    def test_multi_address_entry_is_split_not_collapsed(self):
        sent: list = []
        with _session() as db, \
                patch.object(mail_send_worker.mail_config_service, "get_smtp_config",
                             return_value=READY_CFG), \
                patch.object(mail_send_worker, "_send_one",
                             side_effect=lambda em, cfg=None: sent.append(em)):
            compose_service.compose_and_send(
                db, to_emails=["a@vendor.com; b@vendor.com"],
                cc_emails=["Sales Desk <sales@vendor.com>"], subject="S", body="B",
            )
        em = sent[0]
        self.assertEqual(em["To"], "a@vendor.com, b@vendor.com")
        self.assertEqual(em["Cc"], "sales@vendor.com")

    def test_stored_multi_address_entry_is_cleaned_at_send_time(self):
        # Rows queued by other paths (Email Master values) get the same fix.
        msg = CommunicationMessage(direction="OUTGOING", status="READY",
                                   to_emails=["a@v.com;b@v.com", "", "A@v.com"],
                                   subject="x", body="y")
        em = mail_send_worker._build_email(msg)
        self.assertEqual(em["To"], "a@v.com, b@v.com")

    def test_invalid_address_is_rejected_with_a_clear_error(self):
        with _session() as db:
            with self.assertRaises(HTTPException) as ctx:
                compose_service.compose_and_send(
                    db, to_emails=["vendor@example"], subject="S", body="B", send=False,
                )
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertIn("vendor@example", ctx.exception.detail)

    def test_failed_immediate_send_reports_the_reason_and_stays_queued(self):
        def _boom(em, cfg=None):
            raise OSError("535 authentication failed")

        with _session() as db, \
                patch.object(mail_send_worker.mail_config_service, "get_smtp_config",
                             return_value=READY_CFG), \
                patch.object(mail_send_worker, "_send_one", side_effect=_boom):
            out = compose_service.compose_and_send(
                db, to_emails=["vendor@example.com"], subject="S", body="B",
            )
            msg = db.get(CommunicationMessage, out["message_id"])
        self.assertFalse(out["sent"])
        self.assertTrue(out["will_retry"])
        self.assertIn("535", out["error"])
        self.assertEqual(msg.status, "READY")

    def test_smtp_not_configured_fails_loudly_and_leaves_no_ready_row(self):
        off = SmtpConfig(enabled=False, host="", port=587, user="", password="", from_addr="")
        with _session() as db, \
                patch.object(mail_send_worker.mail_config_service, "get_smtp_config",
                             return_value=off):
            with self.assertRaises(HTTPException) as ctx:
                compose_service.compose_and_send(
                    db, to_emails=["vendor@example.com"], subject="S", body="B",
                )
            self.assertEqual(ctx.exception.status_code, 503)
            statuses = db.scalars(select(CommunicationMessage.status)).all()
        self.assertEqual(statuses, ["FAILED"])

    def test_vendor_ref_links_the_mail_to_the_po_thread(self):
        with _session() as db:
            seeded = _seed_po(db)
            out = compose_service.compose_and_send(
                db, to_emails=["vendor@example.com"], subject="S", body="B",
                supplier_name="Vedant Tools Pvt Ltd", supplier_po_no="2627-001703", send=False,
            )
            msg = db.get(CommunicationMessage, out["message_id"])
            self.assertIn(msg.procurement_record_id, {r.id for r in seeded["recs"][:2]})
            self.assertIn(msg.supplier_po_no, {"000449", "000450"})

    def test_manual_mail_retries_jump_the_auto_followup_backlog(self):
        engine = create_engine("sqlite:///:memory:", future=True,
                               connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        db = Session()
        for i in range(3):
            db.add(CommunicationMessage(direction="OUTGOING", status="READY",
                                        mail_type="PO_FOLLOWUP_RED", subject=f"r{i}",
                                        to_emails=["s@v.com"]))
        db.commit()
        db.add(CommunicationMessage(direction="OUTGOING", status="READY",
                                    mail_type="HUB_COMPOSE", subject="manual",
                                    to_emails=["c@x.com"]))
        db.commit()
        manual_id = db.scalar(select(CommunicationMessage.id).where(
            CommunicationMessage.mail_type == "HUB_COMPOSE"))
        db.close()
        picked: list = []

        def _fake_bucket(ids, schema):
            picked.extend(ids)
            return [{"message_id": i, "status": "SENT"} for i in ids]

        with patch.object(mail_send_worker, "SessionLocal", Session), \
                patch.object(mail_send_worker.mail_config_service, "get_smtp_config",
                             return_value=READY_CFG), \
                patch.object(mail_send_worker, "_send_bucket", side_effect=_fake_bucket):
            mail_send_worker.send_ready_messages(limit=1, now=IST_2300)
        engine.dispose()
        self.assertEqual(picked, [manual_id])


# ── PO acknowledgement ───────────────────────────────────────────────────────
class PoAckTokenTests(unittest.TestCase):
    def test_round_trip(self):
        tok = po_ack_service.make_token(supplier_name="Vedant Tools Pvt Ltd",
                                        supplier_po_no="000449", po_ref="2627-001703",
                                        record_id=7, schema="company_101")
        data = po_ack_service.verify_token(tok)
        self.assertEqual(data["s"], "company_101")
        self.assertEqual(data["n"], "Vedant Tools Pvt Ltd")
        self.assertEqual(data["r"], "2627-001703")
        self.assertEqual(data["i"], 7)

    def test_tampered_payload_or_signature_is_rejected(self):
        tok = po_ack_service.make_token(supplier_name="A", supplier_po_no="1", schema="public")
        body, sig = tok.split(".")
        other = po_ack_service.make_token(supplier_name="B", supplier_po_no="1", schema="public")
        for bad in (f"{other.split('.')[0]}.{sig}", f"{body}.{sig[:-2]}xx", body, "", "a.b"):
            with self.assertRaises(po_ack_service.InvalidAckToken):
                po_ack_service.verify_token(bad)

    def test_link_points_at_the_public_frontend_route(self):
        url = po_ack_service.ack_url("abc.def")
        self.assertTrue(url.endswith("/po-ack/abc.def"))


class PoAcknowledgeTests(unittest.TestCase):
    def test_ack_by_link_is_idempotent_and_notifies_once(self):
        with _session() as db:
            s = _seed_po(db)
            rec = s["recs"][0]
            tok = po_ack_service.make_token(supplier_name=rec.supplier_name,
                                            supplier_po_no=rec.supplier_po_no,
                                            po_ref=rec.po_short_ref, record_id=rec.id)
            first = po_ack_service.acknowledge_by_token(db, tok, ip="1.2.3.4", user_agent="UA")
            second = po_ack_service.acknowledge_by_token(db, tok, ip="5.6.7.8")

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertTrue(second["acknowledged"])
            self.assertEqual(first["acknowledged_at"], second["acknowledged_at"])
            self.assertEqual(first["po_ref"], "2627-001703")

            rows = db.scalars(select(PoAcknowledgement)).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].via, "link")
            self.assertEqual(rows[0].ip, "1.2.3.4")

            # Notified: PO owner + supplier-assigned staff; not the bystander.
            notified = {n.user_id for n in db.scalars(select(Notification)).all()}
            self.assertEqual(notified, {s["owner"].id, s["assigned"].id})
            note = db.scalars(select(Notification)).first()
            self.assertEqual(note.type, "PO_ACK")
            self.assertIn("2627-001703", note.body)
            self.assertIn("Vedant Tools Pvt Ltd", note.body)
            self.assertIn("IST", note.body)

            # One system message in the PO's hub thread.
            msgs = db.scalars(select(CommunicationMessage).where(
                CommunicationMessage.mail_type == "PO_ACK")).all()
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0].supplier_po_no, "000449")
            self.assertEqual(msgs[0].procurement_record_id, rec.id)
            self.assertEqual(msgs[0].supplier_id, s["supplier"].id)
            self.assertIsNone(msgs[0].parsed_status)  # never feeds auto-replies

    def test_portal_ack_on_another_counter_of_the_same_vendor_po_is_the_same_ack(self):
        with _session() as db:
            s = _seed_po(db)
            a, b = s["recs"][0], s["recs"][1]
            _row, created, _ = po_ack_service.acknowledge(
                db, supplier_name=a.supplier_name, supplier_po_no=a.supplier_po_no,
                po_ref=a.po_short_ref, record_id=a.id, via="portal",
            )
            self.assertTrue(created)
            _row2, created2, _ = po_ack_service.acknowledge(
                db, supplier_name=b.supplier_name, supplier_po_no=b.supplier_po_no,
                record_id=b.id, via="link",
            )
            self.assertFalse(created2)
            # The other supplier's PO with the same recycled counter is untouched.
            self.assertIsNone(po_ack_service.find_ack(db, "Other Supplier", "000449", "2627-009999"))

    def test_unknown_po_returns_not_found(self):
        with _session() as db:
            _seed_po(db)
            tok = po_ack_service.make_token(supplier_name="Nobody", supplier_po_no="999")
            out = po_ack_service.acknowledge_by_token(db, tok)
            self.assertFalse(out["found"])
            self.assertEqual(db.scalars(select(PoAcknowledgement)).all(), [])


class PoAckMailAndHubTests(unittest.TestCase):
    def test_followup_mail_has_link_until_acknowledged(self):
        from app.services import po_followup_mail_service as pm

        with _session() as db:
            s = _seed_po(db)
            rec = s["recs"][0]
            group = {"supplier_name": rec.supplier_name, "supplier_po_no": rec.supplier_po_no,
                     "po_ref": rec.po_short_ref, "anchor_record_id": rec.id,
                     "material_count": 2, "overall_signal": "GREEN"}
            url = po_ack_service.ack_url_for_group(db, group)
            self.assertIn("/po-ack/", url)
            html = pm._po_body_html({**group, "ack_url": url}, "<table></table>")
            self.assertIn("Acknowledge PO", html)
            self.assertIn(url, html)
            self.assertNotIn("Acknowledge PO", pm._po_body_html(group, "<table></table>"))

            po_ack_service.acknowledge(db, supplier_name=rec.supplier_name,
                                       supplier_po_no=rec.supplier_po_no,
                                       po_ref=rec.po_short_ref, record_id=rec.id, via="link")
            self.assertIsNone(po_ack_service.ack_url_for_group(db, group))

    def test_hub_po_list_carries_the_ack_time(self):
        from app.routers import communication_hub as hub

        with _session() as db:
            s = _seed_po(db)
            rows = hub._pos_for_supplier(db, s["supplier"].id, "Vedant Tools Pvt Ltd")
            self.assertTrue(rows and all(r["acknowledged_at"] is None for r in rows))
            rec = s["recs"][0]
            po_ack_service.acknowledge(db, supplier_name=rec.supplier_name,
                                       supplier_po_no=rec.supplier_po_no,
                                       po_ref=rec.po_short_ref, record_id=rec.id, via="portal")
            rows = hub._pos_for_supplier(db, s["supplier"].id, "Vedant Tools Pvt Ltd")
            acked = [r for r in rows if r["po_ref"] == "2627-001703"]
            self.assertEqual(len(acked), 1)
            self.assertTrue(acked[0]["acknowledged_at"].endswith("Z"))
            self.assertEqual(acked[0]["acknowledged_via"], "portal")


class PoAckPublicRouteTests(unittest.TestCase):
    def _request(self):
        from starlette.requests import Request

        return Request({
            "type": "http", "method": "POST", "path": "/", "query_string": b"",
            "headers": [(b"x-forwarded-for", b"9.9.9.9, 10.0.0.1"), (b"user-agent", b"TestUA")],
            "client": ("127.0.0.1", 1),
        })

    def test_public_route_records_ip_and_rejects_bad_tokens(self):
        from app.routers import po_ack

        engine = create_engine("sqlite:///:memory:", future=True,
                               connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        db = Session()
        rec = _seed_po(db)["recs"][0]
        tok = po_ack_service.make_token(supplier_name=rec.supplier_name,
                                        supplier_po_no=rec.supplier_po_no,
                                        po_ref=rec.po_short_ref, record_id=rec.id)
        db.close()
        with patch.object(po_ack, "SessionLocal", Session):
            before = po_ack.public_status(tok)
            out = po_ack.public_acknowledge(tok, self._request())
            with self.assertRaises(HTTPException) as ctx:
                po_ack.public_acknowledge(tok[:-3] + "zzz", self._request())
        self.assertFalse(before["acknowledged"])
        self.assertTrue(out["created"])
        self.assertEqual(ctx.exception.status_code, 404)
        db = Session()
        row = db.scalars(select(PoAcknowledgement)).one()
        self.assertEqual((row.ip, row.user_agent), ("9.9.9.9", "TestUA"))
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
