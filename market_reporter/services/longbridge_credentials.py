from __future__ import annotations

import json
from typing import Optional, Tuple

from market_reporter.infra.db.repos import LongbridgeCredentialRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.infra.security.crypto import decrypt_text, encrypt_text
from market_reporter.infra.security.keychain_store import KeychainStore


class LongbridgeCredentialService:
    def __init__(
        self,
        database_url: str,
        user_id: Optional[int] = None,
        keychain_store: Optional[KeychainStore] = None,
    ) -> None:
        self.database_url = database_url
        self.user_id = user_id
        self.keychain_store = keychain_store or KeychainStore(database_url=database_url)

    def upsert(self, app_secret: str, access_token: str) -> None:
        secret = str(app_secret or "").strip()
        token = str(access_token or "").strip()
        if not secret or not token:
            return

        payload = {
            "app_secret": secret,
            "access_token": token,
        }
        master_key = self.keychain_store.get_or_create_master_key()
        ciphertext, nonce = encrypt_text(
            json.dumps(payload, ensure_ascii=False),
            master_key,
        )
        with session_scope(self.database_url) as session:
            repo = LongbridgeCredentialRepo(session)
            repo.upsert(
                credential_ciphertext=ciphertext,
                nonce=nonce,
                user_id=self.user_id,
            )

    def get(self) -> Tuple[str, str]:
        with session_scope(self.database_url) as session:
            repo = LongbridgeCredentialRepo(session)
            row = repo.get(user_id=self.user_id)
            if row is None:
                return "", ""
            ciphertext = row.credential_ciphertext
            nonce = row.nonce

        try:
            master_key = self.keychain_store.get_or_create_master_key()
            raw = decrypt_text(ciphertext, nonce, master_key)
            payload = json.loads(raw)
        except Exception:
            return "", ""

        app_secret = str(payload.get("app_secret") or "").strip()
        access_token = str(payload.get("access_token") or "").strip()
        return app_secret, access_token

    def has_credentials(self) -> bool:
        app_secret, access_token = self.get()
        return bool(app_secret and access_token)

    def delete(self) -> bool:
        with session_scope(self.database_url) as session:
            repo = LongbridgeCredentialRepo(session)
            return repo.delete(user_id=self.user_id)
