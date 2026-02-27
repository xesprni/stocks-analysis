import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from market_reporter.schemas import ReportRunSummary, RunResult
from market_reporter.services.telegram_notifier import TelegramNotifier


class _FakeResponse:
    def raise_for_status(self) -> None:
        return


class _FakeAsyncClient:
    calls = []

    def __init__(self, *args, **kwargs) -> None:
        del args
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def post(self, url, json):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "timeout": self.timeout,
            }
        )
        return _FakeResponse()


class TelegramNotifierTest(unittest.TestCase):
    def test_send_text_returns_false_when_not_ready(self):
        notifier = TelegramNotifier(enabled=True, bot_token="", chat_id="123456")
        sent = asyncio.run(notifier.send_text("hello"))
        self.assertFalse(sent)

    def test_send_text_posts_to_telegram_api(self):
        _FakeAsyncClient.calls.clear()
        notifier = TelegramNotifier(
            enabled=True,
            bot_token="token_abc",
            chat_id="chat_001",
            timeout_seconds=7,
        )
        with patch(
            "market_reporter.services.telegram_notifier.httpx.AsyncClient",
            _FakeAsyncClient,
        ):
            sent = asyncio.run(notifier.send_text("ping"))

        self.assertTrue(sent)
        self.assertEqual(len(_FakeAsyncClient.calls), 1)
        call = _FakeAsyncClient.calls[0]
        self.assertIn("bottoken_abc/sendMessage", call["url"])
        self.assertEqual(call["json"]["chat_id"], "chat_001")
        self.assertEqual(call["json"]["text"], "ping")
        self.assertEqual(call["timeout"], 7)

    def test_notify_report_succeeded_builds_message(self):
        notifier = TelegramNotifier(enabled=True, bot_token="t", chat_id="c")
        captured = {"text": ""}

        async def fake_send_text(text: str) -> bool:
            captured["text"] = text
            return True

        notifier.send_text = fake_send_text  # type: ignore[method-assign]

        summary = ReportRunSummary(
            run_id="20260222_120000",
            generated_at="2026-02-22T12:00:00+08:00",
            report_path=Path("output/20260222_120000/report.md"),
            raw_data_path=Path("output/20260222_120000/raw_data.json"),
            warnings_count=1,
            news_total=12,
            provider_id="mock",
            model="market-default",
            mode="stock",
        )
        result = RunResult(summary=summary, warnings=["fallback used"])

        sent = asyncio.run(notifier.notify_report_succeeded(result=result))
        self.assertTrue(sent)
        self.assertIn("Report completed", captured["text"])
        self.assertIn("run_id: 20260222_120000", captured["text"])
        self.assertIn("mode: stock", captured["text"])
        self.assertIn("warnings: 1", captured["text"])

    def test_notify_report_failed_truncates_long_error(self):
        notifier = TelegramNotifier(enabled=True, bot_token="t", chat_id="c")
        captured = {"text": ""}

        async def fake_send_text(text: str) -> bool:
            captured["text"] = text
            return True

        notifier.send_text = fake_send_text  # type: ignore[method-assign]

        long_error = "x" * 700
        sent = asyncio.run(
            notifier.notify_report_failed(
                error=long_error,
                mode="market",
                skill_id="market_report",
            )
        )

        self.assertTrue(sent)
        self.assertIn("Report failed", captured["text"])
        self.assertIn("skill_id: market_report", captured["text"])
        self.assertTrue(captured["text"].endswith("..."))


if __name__ == "__main__":
    unittest.main()
