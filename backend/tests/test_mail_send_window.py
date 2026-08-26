"""Off-hours auto follow-up send window.

Auto follow-ups (mail_type PO_FOLLOWUP_*) may only leave the outgoing queue
inside a configured overnight window; staff-composed mail is never held. The
window is stored in app_settings and evaluated in the configured timezone,
because the box runs UTC while the office runs IST.
"""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.communication_message import CommunicationMessage
from app.services import settings_service as svc

# IST is UTC+5:30. These are the UTC instants for the IST wall-clock times the
# office actually cares about, so the tests fail if the conversion is dropped.
IST_1900 = datetime(2026, 8, 26, 13, 30)
IST_2300 = datetime(2026, 8, 26, 17, 30)
IST_0200 = datetime(2026, 8, 26, 20, 30)
IST_0759 = datetime(2026, 8, 26, 2, 29)
IST_0800 = datetime(2026, 8, 26, 2, 30)
IST_1200 = datetime(2026, 8, 26, 6, 30)
IST_1859 = datetime(2026, 8, 26, 13, 29)


@contextmanager
def _temp_db():
    # StaticPool keeps every session on ONE connection; without it each new
    # SessionLocal() would get its own empty :memory: database.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield Session
    finally:
        engine.dispose()


def _cfg(**over) -> dict:
    return {**svc.DEFAULT_MAIL_SEND_WINDOW, **over}


class WindowPredicateTests(unittest.TestCase):
    """window_is_open handles the midnight wrap (start 19 > end 8)."""

    def test_open_inside_the_overnight_window(self) -> None:
        open_at = [svc.window_is_open(_cfg(), m)
                   for m in (IST_1900, IST_2300, IST_0200, IST_0759)]
        self.assertEqual(open_at, [True, True, True, True],
                         "19:00, 23:00, 02:00 and 07:59 IST are all inside the window")

    def test_closed_during_office_hours(self) -> None:
        open_at = [svc.window_is_open(_cfg(), m)
                   for m in (IST_0800, IST_1200, IST_1859)]
        self.assertEqual(open_at, [False, False, False],
                         "08:00, 12:00 and 18:59 IST are office hours")

    def test_disabled_window_never_holds_anything(self) -> None:
        self.assertTrue(svc.window_is_open(_cfg(enabled=False), IST_1200))

    def test_equal_start_and_end_hour_is_always_open(self) -> None:
        cfg = _cfg(start_hour=8, end_hour=8)
        self.assertTrue(svc.window_is_open(cfg, IST_1200))
        self.assertTrue(svc.window_is_open(cfg, IST_0200))

    def test_daytime_window_does_not_wrap(self) -> None:
        cfg = _cfg(start_hour=9, end_hour=17)
        self.assertTrue(svc.window_is_open(cfg, IST_1200))
        self.assertFalse(svc.window_is_open(cfg, IST_2300))


class WindowSettingTests(unittest.TestCase):
    def test_defaults_apply_when_no_row_exists(self) -> None:
        with _temp_db() as Session:
            db = Session()
            cfg = svc.get_mail_send_window(db)
            db.close()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["start_hour"], 19)
        self.assertEqual(cfg["end_hour"], 8)
        self.assertEqual(cfg["per_minute_limit"], 25)
        self.assertEqual(cfg["timezone"], "Asia/Kolkata")

    def test_out_of_range_values_are_clamped(self) -> None:
        with _temp_db() as Session:
            db = Session()
            cfg = svc.set_mail_send_window(
                db, {"start_hour": 99, "end_hour": -4, "per_minute_limit": 0}
            )
            db.close()
        self.assertEqual(cfg["start_hour"], 23)
        self.assertEqual(cfg["end_hour"], 0)
        self.assertEqual(cfg["per_minute_limit"], 1)

    def test_partial_update_persists_and_keeps_the_other_fields(self) -> None:
        # Read back through a SEPARATE session: a same-session read can be served
        # from SQLAlchemy's identity map even when the JSON column was never
        # marked dirty, which would hide a lost write.
        with _temp_db() as Session:
            writer = Session()
            svc.set_mail_send_window(writer, {"per_minute_limit": 12})
            writer.close()

            reader = Session()
            cfg = svc.get_mail_send_window(reader)
            reader.close()
        self.assertEqual(cfg["per_minute_limit"], 12)
        self.assertEqual(cfg["start_hour"], 19)


class WorkerGateTests(unittest.TestCase):
    """send_ready_messages must hold auto follow-ups outside the window only."""

    def _seed(self, Session) -> dict[str, int]:
        db = Session()
        rows = {
            "auto_red": CommunicationMessage(
                direction="OUTGOING", status="READY", mail_type="PO_FOLLOWUP_RED",
                subject="Auto red", to_emails=["s@v.com"],
            ),
            "auto_group": CommunicationMessage(
                direction="OUTGOING", status="READY", mail_type="PO_FOLLOWUP_GROUP",
                subject="Auto group", to_emails=["s@v.com"],
            ),
            "staff_typed": CommunicationMessage(
                direction="OUTGOING", status="READY", mail_type="CUSTOMER_REPLY",
                subject="Staff reply", to_emails=["c@x.com"],
            ),
            "staff_untyped": CommunicationMessage(
                direction="OUTGOING", status="READY", mail_type=None,
                subject="Compose", to_emails=["c@x.com"],
            ),
        }
        for row in rows.values():
            db.add(row)
        db.commit()
        ids = {name: row.id for name, row in rows.items()}
        db.close()
        return ids

    @contextmanager
    def _worker(self, Session, cfg: dict | None = None):
        """Patch the worker's DB + SMTP so only the selection logic is exercised."""
        from unittest.mock import patch

        from app.workers import mail_send_worker as w

        sent: list[int] = []

        def _fake_bucket(message_ids, schema):
            sent.extend(message_ids)
            return [{"id": i, "status": "SENT"} for i in message_ids]

        db = Session()
        if cfg is not None:
            svc.set_mail_send_window(db, cfg)
        db.close()

        ready_cfg = type("C", (), {"ready": lambda self: (True, "")})()
        with (
            patch.object(w, "SessionLocal", Session),
            patch.object(w.mail_config_service, "get_smtp_config", return_value=ready_cfg),
            patch.object(w, "_send_bucket", side_effect=_fake_bucket),
        ):
            yield w, sent

    def test_closed_window_holds_auto_followups_but_sends_staff_mail(self) -> None:
        with _temp_db() as Session:
            ids = self._seed(Session)
            with self._worker(Session) as (w, sent):
                out = w.send_ready_messages(now=IST_1200)

        self.assertNotIn(ids["auto_red"], sent)
        self.assertNotIn(ids["auto_group"], sent)
        self.assertIn(ids["staff_typed"], sent)
        self.assertIn(ids["staff_untyped"], sent)
        self.assertFalse(out["window_open"])

    def test_open_window_sends_auto_followups_too(self) -> None:
        with _temp_db() as Session:
            ids = self._seed(Session)
            with self._worker(Session) as (w, sent):
                out = w.send_ready_messages(now=IST_2300)

        self.assertEqual(set(sent), set(ids.values()))
        self.assertTrue(out["window_open"])

    def test_batch_limit_comes_from_the_configured_per_minute_limit(self) -> None:
        with _temp_db() as Session:
            self._seed(Session)
            with self._worker(Session, cfg={"per_minute_limit": 2}) as (w, sent):
                out = w.send_ready_messages(now=IST_2300)

        self.assertEqual(out["attempted"], 2)
        self.assertEqual(len(sent), 2)


if __name__ == "__main__":
    unittest.main()


class NextWindowChangeTests(unittest.TestCase):
    """The admin card needs to say when the window next flips."""

    def test_reports_the_closing_hour_while_open(self) -> None:
        self.assertEqual(svc.next_window_change(_cfg(), IST_2300), "08:00")

    def test_reports_the_opening_hour_while_closed(self) -> None:
        self.assertEqual(svc.next_window_change(_cfg(), IST_1200), "19:00")

    def test_blank_when_the_window_never_closes(self) -> None:
        self.assertEqual(svc.next_window_change(_cfg(enabled=False), IST_1200), "")
        self.assertEqual(svc.next_window_change(_cfg(start_hour=8, end_hour=8), IST_1200), "")
