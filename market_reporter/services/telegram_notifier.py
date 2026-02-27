from __future__ import annotations

import logging
from typing import Optional

import httpx

from market_reporter.config import TelegramConfig
from market_reporter.schemas import RunResult

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self,
        *,
        enabled: bool,
        bot_token: str,
        chat_id: str,
        timeout_seconds: int = 10,
    ) -> None:
        self.enabled = bool(enabled)
        self.bot_token = str(bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.timeout_seconds = max(3, int(timeout_seconds))

    @classmethod
    def from_config(cls, config: TelegramConfig) -> "TelegramNotifier":
        return cls(
            enabled=config.enabled,
            bot_token=config.bot_token,
            chat_id=config.chat_id,
            timeout_seconds=config.timeout_seconds,
        )

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.bot_token and self.chat_id)

    async def send_text(self, text: str) -> bool:
        if not self.ready:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("telegram send failed: %s", exc)
            return False

    async def notify_report_succeeded(self, result: RunResult) -> bool:
        summary = result.summary
        lines = [
            "[Market Reporter] Report completed",
            f"run_id: {summary.run_id}",
            f"mode: {summary.mode or 'market'}",
            f"provider/model: {summary.provider_id} / {summary.model}",
            f"warnings: {len(result.warnings)}",
            f"generated_at: {summary.generated_at}",
        ]
        return await self.send_text("\n".join(lines))

    async def notify_report_failed(
        self,
        *,
        error: str,
        mode: str,
        skill_id: Optional[str] = None,
    ) -> bool:
        message = str(error or "unknown error").strip()
        if len(message) > 600:
            message = f"{message[:600]}..."
        lines = [
            "[Market Reporter] Report failed",
            f"mode: {mode or 'market'}",
        ]
        if skill_id:
            lines.append(f"skill_id: {skill_id}")
        lines.append(f"error: {message}")
        return await self.send_text("\n".join(lines))
