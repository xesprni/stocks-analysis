from __future__ import annotations

import base64
import os
from pathlib import Path

import keyring
from keyring.errors import KeyringError

from market_reporter.core.errors import SecretStorageError
from market_reporter.infra.security.crypto import generate_master_key


class KeychainStore:
    def __init__(
        self,
        service_name: str = "market-reporter",
        account: str = "master-key",
        master_key_file: str | None = None,
    ) -> None:
        self.service_name = service_name
        self.account = account
        value = (master_key_file or os.getenv("MARKET_REPORTER_MASTER_KEY_FILE", "")).strip()
        self.master_key_file = Path(value).expanduser() if value else None

    def get_or_create_master_key(self) -> bytes:
        if self.master_key_file is not None and self.master_key_file.exists():
            encoded = self.master_key_file.read_text(encoding="utf-8").strip()
            if encoded:
                try:
                    return base64.b64decode(encoded.encode("utf-8"))
                except Exception as exc:
                    raise SecretStorageError(
                        f"Corrupted master key file: {self.master_key_file}"
                    ) from exc

        try:
            value = keyring.get_password(self.service_name, self.account)
        except KeyringError as exc:
            if self.master_key_file is not None:
                return self._read_or_create_file_key()
            raise SecretStorageError(f"Failed to access macOS Keychain: {exc}") from exc

        if value:
            try:
                return base64.b64decode(value.encode("utf-8"))
            except Exception as exc:
                raise SecretStorageError("Corrupted master key in Keychain") from exc

        key = generate_master_key()
        try:
            keyring.set_password(
                self.service_name,
                self.account,
                base64.b64encode(key).decode("utf-8"),
            )
        except KeyringError as exc:
            if self.master_key_file is not None:
                self._write_key_file(key)
                return key
            raise SecretStorageError(f"Failed to write master key into Keychain: {exc}") from exc
        return key

    def _read_or_create_file_key(self) -> bytes:
        if self.master_key_file is None:
            raise SecretStorageError("Master key file fallback is not configured.")
        if self.master_key_file.exists():
            encoded = self.master_key_file.read_text(encoding="utf-8").strip()
            if encoded:
                try:
                    return base64.b64decode(encoded.encode("utf-8"))
                except Exception as exc:
                    raise SecretStorageError(
                        f"Corrupted master key file: {self.master_key_file}"
                    ) from exc
        key = generate_master_key()
        self._write_key_file(key)
        return key

    def _write_key_file(self, key: bytes) -> None:
        if self.master_key_file is None:
            raise SecretStorageError("Master key file fallback is not configured.")
        self.master_key_file.parent.mkdir(parents=True, exist_ok=True)
        self.master_key_file.write_text(
            base64.b64encode(key).decode("utf-8"),
            encoding="utf-8",
        )
