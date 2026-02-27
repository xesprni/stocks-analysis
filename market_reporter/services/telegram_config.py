from __future__ import annotations

import json
from typing import Optional

from market_reporter.config import TelegramConfig
from market_reporter.infra.db.repos import TelegramConfigRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.infra.security.crypto import decrypt_text, encrypt_text
from market_reporter.infra.security.keychain_store import KeychainStore


class TelegramConfigService:
    def __init__(
        self,
        database_url: str,
        keychain_store: Optional[KeychainStore] = None,
    ) -> None:
        self.database_url = database_url
        self.keychain_store = keychain_store or KeychainStore()

    def upsert(
        self,
        *,
        enabled: bool,
        chat_id: str,
        bot_token: str,
        timeout_seconds: int,
    ) -> None:
        payload = {
            "enabled": bool(enabled),
            "chat_id": str(chat_id or "").strip(),
            "bot_token": str(bot_token or "").strip(),
            "timeout_seconds": int(timeout_seconds),
        }
        master_key = self.keychain_store.get_or_create_master_key()
        ciphertext, nonce = encrypt_text(
            json.dumps(payload, ensure_ascii=False),
            master_key,
        )
        with session_scope(self.database_url) as session:
            repo = TelegramConfigRepo(session)
            repo.upsert(config_ciphertext=ciphertext, nonce=nonce)

    def get(self) -> TelegramConfig:
        with session_scope(self.database_url) as session:
            repo = TelegramConfigRepo(session)
            row = repo.get()
            if row is None:
                return TelegramConfig()
            ciphertext = row.config_ciphertext
            nonce = row.nonce

        try:
            master_key = self.keychain_store.get_or_create_master_key()
            raw = decrypt_text(ciphertext, nonce, master_key)
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return TelegramConfig()
        except Exception:
            return TelegramConfig()

        chat_id = str(payload.get("chat_id") or "").strip()
        bot_token = str(payload.get("bot_token") or "").strip()
        timeout_raw = payload.get("timeout_seconds", 10)
        try:
            timeout_seconds = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_seconds = 10
        timeout_seconds = min(60, max(3, timeout_seconds))
        enabled = bool(payload.get("enabled") and chat_id and bot_token)
        return TelegramConfig(
            enabled=enabled,
            chat_id=chat_id,
            bot_token=bot_token,
            timeout_seconds=timeout_seconds,
        )

    def has_config(self) -> bool:
        config = self.get()
        return bool(config.chat_id and config.bot_token)

    def delete(self) -> bool:
        with session_scope(self.database_url) as session:
            repo = TelegramConfigRepo(session)
            return repo.delete()
