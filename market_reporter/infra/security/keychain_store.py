from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional

import keyring
from keyring.errors import KeyringError

from market_reporter.core.errors import SecretStorageError
from market_reporter.infra.security.crypto import generate_master_key


def resolve_master_key_file(
    *,
    master_key_file: Optional[str] = None,
    database_url: Optional[str] = None,
) -> Path:
    configured = (
        master_key_file or os.getenv("MARKET_REPORTER_MASTER_KEY_FILE", "")
    ).strip()
    if configured:
        return Path(configured).expanduser()

    db_url = str(database_url or "").strip()
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", "", 1)).expanduser()
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        return db_path.parent / "master_key.b64"

    return Path.home() / ".market-reporter" / "master_key.b64"


class KeychainStore:
    def __init__(
        self,
        service_name: str = "market-reporter",
        account: str = "master-key",
        master_key_file: str | None = None,
        database_url: str | None = None,
    ) -> None:
        self.service_name = service_name
        self.account = account
        self.master_key_file = resolve_master_key_file(
            master_key_file=master_key_file,
            database_url=database_url,
        )

    def get_or_create_master_key(self) -> bytes:
        key_from_env = self._read_master_key_from_env()
        if key_from_env is not None:
            self._try_write_key_file(key_from_env)
            return key_from_env

        if self.master_key_file.exists():
            return self._read_key_file(self.master_key_file)

        keyring_read_error: Optional[Exception] = None
        value: Optional[str] = None

        try:
            value = keyring.get_password(self.service_name, self.account)
        except KeyringError as exc:
            keyring_read_error = exc

        if value:
            key = self._decode_master_key(value.strip(), source="keyring")
            self._try_write_key_file(key)
            return key

        key = generate_master_key()
        keyring_write_error: Optional[Exception] = None
        try:
            keyring.set_password(
                self.service_name,
                self.account,
                base64.b64encode(key).decode("utf-8"),
            )
        except KeyringError as exc:
            keyring_write_error = exc

        wrote_to_file = self._try_write_key_file(key)
        if wrote_to_file or keyring_write_error is None:
            return key

        reasons = []
        if keyring_read_error is not None:
            reasons.append(f"keyring read failed: {keyring_read_error}")
        if keyring_write_error is not None:
            reasons.append(f"keyring write failed: {keyring_write_error}")
        raise SecretStorageError(
            "Failed to persist master key; "
            + "; ".join(reasons)
            + f"; file fallback path={self.master_key_file}"
        )

    def _write_key_file(self, key: bytes) -> None:
        self.master_key_file.parent.mkdir(parents=True, exist_ok=True)
        self.master_key_file.write_text(
            base64.b64encode(key).decode("utf-8"),
            encoding="utf-8",
        )
        try:
            os.chmod(self.master_key_file, 0o600)
        except Exception:
            pass

    def _read_key_file(self, path: Path) -> bytes:
        encoded = path.read_text(encoding="utf-8").strip()
        if not encoded:
            raise SecretStorageError(f"Corrupted master key file: {path}")
        return self._decode_master_key(encoded, source=f"file:{path}")

    def _try_write_key_file(self, key: bytes) -> bool:
        try:
            self._write_key_file(key)
            return True
        except Exception:
            return False

    @staticmethod
    def _read_master_key_from_env() -> Optional[bytes]:
        raw = os.getenv("MARKET_REPORTER_MASTER_KEY", "").strip()
        if not raw:
            return None
        return KeychainStore._decode_master_key(
            raw,
            source="env:MARKET_REPORTER_MASTER_KEY",
        )

    @staticmethod
    def _decode_master_key(encoded: str, *, source: str) -> bytes:
        try:
            decoded = base64.b64decode(encoded.encode("utf-8"), validate=True)
        except Exception as exc:
            raise SecretStorageError(f"Corrupted master key from {source}") from exc
        if len(decoded) != 32:
            raise SecretStorageError(
                f"Invalid master key length from {source}: expected 32 bytes"
            )
        return decoded
