"""Tests for the OpenAI (gpt-5-nano) secondary provider routing in ai_service.

Covers: provider ordering (HI chat prefers gpt-5-nano), fallback from the
primary endpoint, gpt-5 request params (no temperature/max_tokens, uses
max_completion_tokens + reasoning_effort + prompt_cache_key), and the flex
service tier for background/cron traffic with a standard-tier retry.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services import ai_service


def _completion(content: str = "ok"):
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeClient:
    """Captures chat.completions.create kwargs; pops queued results/exceptions."""

    def __init__(self, results=None):
        self.calls: list[dict] = []
        self._results = list(results or [])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        nxt = self._results.pop(0) if self._results else _completion()
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _both_enabled():
    return patch.multiple(
        settings,
        LLM_ENABLED=True, LLM_API_KEY="nv-key",
        OPENAI_ENABLED=True, OPENAI_API_KEY="sk-test",
    )


class ProviderOrderTests(unittest.TestCase):
    def test_prefer_openai_puts_nano_first(self) -> None:
        with _both_enabled():
            self.assertEqual(ai_service._provider_order(True), ["openai", "primary"])
            self.assertEqual(ai_service._provider_order(False), ["primary", "openai"])

    def test_openai_only(self) -> None:
        with patch.multiple(settings, LLM_ENABLED=False,
                            OPENAI_ENABLED=True, OPENAI_API_KEY="sk-test"):
            self.assertEqual(ai_service._provider_order(False), ["openai"])
            self.assertEqual(ai_service._provider_order(True), ["openai"])

    def test_none_enabled_raises(self) -> None:
        with patch.multiple(settings, LLM_ENABLED=False, OPENAI_ENABLED=False):
            with self.assertRaises(ai_service.AIDisabledError):
                ai_service._complete([{"role": "user", "content": "hi"}])


class OpenAICompleteTests(unittest.TestCase):
    def test_gpt5_params_and_cache_key(self) -> None:
        fake = _FakeClient()
        primary = MagicMock()
        with _both_enabled(), \
                patch.object(ai_service, "_openai_client", return_value=fake), \
                patch.object(ai_service, "_client", primary):
            out = ai_service._complete(
                [{"role": "user", "content": "hi"}],
                prefer_openai=True, cache_key="hi-agent",
            )
        self.assertEqual(out, "ok")
        primary.assert_not_called()
        kw = fake.calls[0]
        self.assertEqual(kw["model"], settings.OPENAI_MODEL)
        self.assertNotIn("temperature", kw)   # gpt-5 only accepts the default
        self.assertNotIn("top_p", kw)
        self.assertNotIn("max_tokens", kw)    # gpt-5 rejects max_tokens
        extra = kw["extra_body"]
        self.assertGreaterEqual(extra["max_completion_tokens"],
                                settings.OPENAI_MAX_COMPLETION_TOKENS)
        self.assertEqual(extra["prompt_cache_key"], "sfm-hi-agent")
        self.assertNotIn("service_tier", extra)  # interactive → standard tier

    def test_background_uses_flex_tier(self) -> None:
        fake = _FakeClient()
        with _both_enabled(), patch.object(ai_service, "_openai_client", return_value=fake):
            ai_service._openai_complete([{"role": "user", "content": "hi"}], background=True)
        self.assertEqual(fake.calls[0]["extra_body"]["service_tier"], "flex")

    def test_flex_failure_retries_standard_tier(self) -> None:
        fake = _FakeClient(results=[RuntimeError("capacity shed"), _completion("second")])
        with _both_enabled(), patch.object(ai_service, "_openai_client", return_value=fake):
            out = ai_service._openai_complete([{"role": "user", "content": "hi"}], background=True)
        self.assertEqual(out, "second")
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[0]["extra_body"].get("service_tier"), "flex")
        self.assertNotIn("service_tier", fake.calls[1]["extra_body"])

    def test_primary_failure_falls_back_to_openai(self) -> None:
        primary = _FakeClient(results=[RuntimeError("nim down")])
        backup = _FakeClient(results=[_completion("from-nano")])
        with _both_enabled(), \
                patch.object(ai_service, "_client", return_value=primary), \
                patch.object(ai_service, "_openai_client", return_value=backup), \
                patch.object(ai_service, "_prompt", lambda key: "sys"):
            out = ai_service.summarize_thread("some transcript", background=True)
        self.assertEqual(out, "from-nano")
        self.assertEqual(len(primary.calls), 1)
        # Cron/backend backup call rides the cheap flex tier.
        self.assertEqual(backup.calls[0]["extra_body"].get("service_tier"), "flex")


class AgentRoutingTests(unittest.TestCase):
    def test_hi_chat_prefers_openai(self) -> None:
        backup = _FakeClient(results=[_completion("nano reply")])
        primary = MagicMock()
        with _both_enabled(), \
                patch.object(ai_service, "_client", primary), \
                patch.object(ai_service, "_openai_client", return_value=backup):
            result = ai_service.chat_with_tools(
                [{"role": "user", "content": "draft a reply"}],
                tools=[{"type": "function", "function": {"name": "t", "parameters": {}}}],
                executor=lambda name, args: {},
                system="test system",
                prefer_openai=True,
                cache_key="hi-agent",
            )
        self.assertEqual(result["reply"], "nano reply")
        primary.assert_not_called()
        kw = backup.calls[0]
        self.assertEqual(kw["model"], settings.OPENAI_MODEL)
        self.assertEqual(kw["extra_body"]["prompt_cache_key"], "sfm-hi-agent")

    def test_force_tools_first_requires_tool_call(self) -> None:
        backup = _FakeClient(results=[_completion("done")])
        with _both_enabled(), patch.object(ai_service, "_openai_client", return_value=backup):
            ai_service.chat_with_tools(
                [{"role": "user", "content": "send it"}],
                tools=[{"type": "function", "function": {"name": "t", "parameters": {}}}],
                executor=lambda name, args: {},
                system="test system",
                prefer_openai=True,
                force_tools_first=True,
            )
        self.assertEqual(backup.calls[0]["tool_choice"], "required")

    def test_agent_switches_provider_on_failure(self) -> None:
        primary = _FakeClient(results=[RuntimeError("nim down")])
        backup = _FakeClient(results=[_completion("recovered")])
        with _both_enabled(), \
                patch.object(ai_service, "_client", return_value=primary), \
                patch.object(ai_service, "_openai_client", return_value=backup):
            result = ai_service.chat_with_tools(
                [{"role": "user", "content": "hello"}],
                tools=[],
                executor=lambda name, args: {},
                system="test system",
            )
        self.assertEqual(result["reply"], "recovered")
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(backup.calls), 1)


if __name__ == "__main__":
    unittest.main()
