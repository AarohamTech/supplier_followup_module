"""S3 chat attachments: storage service, message binding, scoped downloads,
the hub-reply flow, and email MIME attachment.

Storage is faked with an in-memory dict so no network/boto3 is exercised.
"""
import io
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_attachments.sqlite")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import CommunicationMessage, ProcurementRecord, SupplierMaster  # noqa: E402
from app.routers import communication_hub as hub  # noqa: E402
from app.routers import employee_portal, portal  # noqa: E402
from app.services import attachment_service as svc  # noqa: E402
from app.services import user_service  # noqa: E402
from app.workers.mail_send_worker import _build_email  # noqa: E402


class _FakeS3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.objects[Key] = bytes(Body)

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[Key])}


@contextmanager
def _env():
    """In-memory DB + fake S3 + enabled storage settings."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Session()
    fake = _FakeS3()
    try:
        with patch.object(svc, "_client", return_value=fake), \
             patch.object(settings, "S3_BUCKET", "test-bucket"), \
             patch.object(settings, "S3_ACCESS_KEY_ID", "k"), \
             patch.object(settings, "S3_SECRET_ACCESS_KEY", "s"):
            yield db, fake
    finally:
        db.close()
        engine.dispose()


def _seed_supplier(db):
    sup = SupplierMaster(supplier_name="ACME TOOLS", is_active=True)
    db.add(sup)
    db.commit()
    db.refresh(sup)
    supplier_user = user_service.create_user(
        db, email="sup@acme.local", password="pw", full_name="Acme",
        role="supplier", supplier_id=sup.id,
    )
    db.add(ProcurementRecord(
        crm_no="C1", supplier_po_no="PO-1", material_name="Drill",
        supplier_name="ACME TOOLS", owner_emp_code="E1", po_trn_no="TRN1",
    ))
    db.commit()
    return sup, supplier_user


class ServiceTests(unittest.TestCase):
    def test_save_bind_and_roundtrip(self):
        with _env() as (db, fake):
            att = svc.save_upload(
                db, data=b"hello", filename="../weird/na me?.pdf", content_type="application/pdf",
                uploaded_by_kind="staff", uploaded_by_id=1,
            )
            self.assertEqual(att.filename, "na me_.pdf")  # path + odd chars stripped
            self.assertEqual(svc.get_bytes(att), b"hello")
            self.assertEqual(len(fake.objects), 1)

            bound = svc.bind(db, 99, [att.id], expect_kind="staff", expect_uploader_id=1)
            self.assertEqual([a.id for a in bound], [att.id])
            # Already bound → cannot be bound again (or stolen).
            self.assertEqual(svc.bind(db, 100, [att.id]), [])

    def test_bind_rejects_other_uploader(self):
        with _env() as (db, _):
            att = svc.save_upload(
                db, data=b"x", filename="a.txt", content_type="text/plain",
                uploaded_by_kind="supplier", uploaded_by_id=7, supplier_id=1,
            )
            self.assertEqual(svc.bind(db, 1, [att.id], expect_kind="supplier", expect_uploader_id=8), [])
            self.assertEqual(len(svc.bind(db, 1, [att.id], expect_kind="supplier", expect_uploader_id=7)), 1)

    def test_size_limit_and_disabled(self):
        with _env() as (db, _):
            with patch.object(settings, "ATTACHMENT_MAX_MB", 1):
                with self.assertRaises(ValueError):
                    svc.save_upload(
                        db, data=b"x" * (1024 * 1024 + 1), filename="big.bin", content_type=None,
                        uploaded_by_kind="staff", uploaded_by_id=1,
                    )
            with patch.object(settings, "S3_BUCKET", ""):
                self.assertFalse(svc.storage_enabled())
                with self.assertRaises(ValueError):
                    svc.save_upload(
                        db, data=b"x", filename="a", content_type=None,
                        uploaded_by_kind="staff", uploaded_by_id=1,
                    )


class PortalFlowTests(unittest.TestCase):
    def test_supplier_message_carries_attachment_and_download_is_scoped(self):
        with _env() as (db, _):
            sup, supplier_user = _seed_supplier(db)
            att = svc.save_upload(
                db, data=b"drawing", filename="drawing.pdf", content_type="application/pdf",
                uploaded_by_kind="supplier", uploaded_by_id=supplier_user.id, supplier_id=sup.id,
            )
            from app.schemas.portal import PortalMessageCreate

            msg = portal.post_po_message(
                supplier_po_no="PO-1",
                payload=PortalMessageCreate(body="see file", attachment_ids=[att.id]),
                user=supplier_user,
                db=db,
            )
            self.assertEqual([a.filename for a in msg.attachments], ["drawing.pdf"])

            listed = portal.list_po_messages(supplier_po_no="PO-1", user=supplier_user, db=db)
            self.assertEqual(len(listed[-1].attachments), 1)

            # The owning supplier downloads fine.
            resp = portal.download_attachment(att.id, user=supplier_user, db=db)
            self.assertEqual(resp.body, b"drawing")

            # A different supplier gets 404.
            other_sup = SupplierMaster(supplier_name="OTHER", is_active=True)
            db.add(other_sup)
            db.commit()
            other_user = user_service.create_user(
                db, email="other@x.local", password="pw", role="supplier", supplier_id=other_sup.id,
            )
            with self.assertRaises(HTTPException) as ctx:
                portal.download_attachment(att.id, user=other_user, db=db)
            self.assertEqual(ctx.exception.status_code, 404)

    def test_employee_download_scope(self):
        with _env() as (db, _):
            sup, supplier_user = _seed_supplier(db)
            e1 = user_service.create_user(
                db, email="e1@x.local", password="pw", role="employee", emp_code="E1", username="D1",
            )
            e2 = user_service.create_user(
                db, email="e2@x.local", password="pw", role="employee", emp_code="E2", username="D2",
            )
            att = svc.save_upload(
                db, data=b"f", filename="f.txt", content_type="text/plain",
                uploaded_by_kind="supplier", uploaded_by_id=supplier_user.id, supplier_id=sup.id,
            )
            cm = CommunicationMessage(
                direction="INCOMING", status="RECEIVED", supplier_id=sup.id,
                supplier_name="ACME TOOLS", supplier_po_no="PO-1", subject="s", body="b",
            )
            db.add(cm)
            db.commit()
            svc.bind(db, cm.id, [att.id])

            # E1 owns PO-1 → allowed; E2 does not → 404.
            self.assertEqual(employee_portal.download_attachment(att.id, user=e1, db=db).body, b"f")
            with self.assertRaises(HTTPException):
                employee_portal.download_attachment(att.id, user=e2, db=db)


class HubReplyTests(unittest.TestCase):
    def test_portal_only_reply_binds_attachments(self):
        with _env() as (db, _):
            _seed_supplier(db)
            att = svc.save_upload(
                db, data=b"note", filename="note.txt", content_type="text/plain",
                uploaded_by_kind="staff", uploaded_by_id=1,
            )
            res = hub.reply_now(
                hub.HubReplyIn(
                    supplier_po_no="PO-1", supplier_name="ACME TOOLS",
                    body="see attachment", send_email=False, attachment_ids=[att.id],
                ),
                db=db,
            )
            self.assertTrue(res["ok"])
            db.refresh(att)
            self.assertEqual(att.message_id, res["message_id"])

    def test_email_build_includes_attachment(self):
        with _env() as (db, _):
            cm = CommunicationMessage(
                direction="OUTGOING", status="READY", subject="Hi", body="body",
                to_emails=["a@b.c"],
            )
            db.add(cm)
            db.commit()
            att = svc.save_upload(
                db, data=b"%PDF-x", filename="doc.pdf", content_type="application/pdf",
                uploaded_by_kind="staff", uploaded_by_id=1,
            )
            svc.bind(db, cm.id, [att.id])
            with patch.object(settings, "SMTP_FROM", "noreply@x.local"):
                em = _build_email(cm, db=db)
            parts = list(em.iter_attachments())
            self.assertEqual(len(parts), 1)
            self.assertEqual(parts[0].get_filename(), "doc.pdf")
            self.assertEqual(parts[0].get_content_type(), "application/pdf")


if __name__ == "__main__":
    unittest.main()
