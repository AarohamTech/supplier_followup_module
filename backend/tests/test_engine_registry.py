"""Tests for the engine job registry."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import engine_registry
from app.services.engine_registry import EngineJobSpec


class EngineRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original = dict(engine_registry._REGISTRY)
        engine_registry._REGISTRY.clear()

    def tearDown(self) -> None:
        engine_registry._REGISTRY.clear()
        engine_registry._REGISTRY.update(self._original)

    def test_register_and_get_spec(self) -> None:
        spec = EngineJobSpec(
            job_name="test_job",
            display_name="Test",
            description="desc",
            default_interval_minutes=5,
            runner=lambda: {"attempted": 0},
        )
        engine_registry.register(spec)
        self.assertIs(engine_registry.get_spec("test_job"), spec)
        self.assertIn(spec, engine_registry.all_specs())

    def test_extract_counts_from_send_worker_result(self) -> None:
        result = {
            "attempted": 3,
            "results": [
                {"status": "SENT"},
                {"status": "SENT"},
                {"status": "FAILED"},
            ],
        }
        self.assertEqual(engine_registry._extract_counts(result), (3, 2, 1))

    def test_extract_counts_handles_queue_result(self) -> None:
        result = {"queued": 4, "skipped": 1, "enabled": True}
        self.assertEqual(engine_registry._extract_counts(result), (4, 0, 0))

    def test_extract_counts_aggregates_per_company_queue_result(self) -> None:
        # Per-company runners (Task 4) return {code: {...}} instead of a flat
        # dict. The counter projection must sum across companies.
        result = {"101": {"queued": 3, "skipped": 1}, "102": {"queued": 2}}
        processed, success, failed = engine_registry._extract_counts(result)
        self.assertEqual(processed, 5)

    def test_extract_counts_flat_dict_not_aggregated(self) -> None:
        # A flat dict (values are not all dicts) must NOT be mistaken for the
        # per-company shape and must not be accidentally aggregated.
        result = {"enabled": False, "status": "DISABLED"}
        self.assertEqual(engine_registry._extract_counts(result), (0, 0, 0))

    def test_extract_counts_aggregates_per_company_results_lists(self) -> None:
        result = {
            "101": {"results": [{"status": "SENT"}]},
            "102": {"results": [{"status": "SENT"}, {"status": "FAILED"}]},
        }
        processed, success, failed = engine_registry._extract_counts(result)
        self.assertEqual(success, 2)
        self.assertEqual(failed, 1)

    def test_run_job_returns_error_for_unknown_job(self) -> None:
        out = engine_registry.run_job("does_not_exist")
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "ERROR")
        self.assertIn("Unknown job", out["message"])

    @patch("app.services.engine_registry.SessionLocal")
    def test_run_job_invokes_runner_and_returns_status(self, session_local) -> None:
        # If the DB session calls fail (e.g. no DB), the wrapper must still
        # invoke the runner and report status.
        session_local.return_value.__enter__ = lambda self: self
        session_local.return_value.__exit__ = lambda *args: False
        session_local.side_effect = RuntimeError("no db")

        invoked = []

        def runner():
            invoked.append(True)
            return {"attempted": 1, "results": [{"status": "SENT"}]}

        engine_registry.register(
            EngineJobSpec(
                job_name="ok_job",
                display_name="OK",
                description="",
                default_interval_minutes=5,
                runner=runner,
            )
        )

        out = engine_registry.run_job("ok_job", manual=True)
        self.assertTrue(invoked)
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["records_processed"], 1)
        self.assertEqual(out["records_success"], 1)


if __name__ == "__main__":
    unittest.main()
