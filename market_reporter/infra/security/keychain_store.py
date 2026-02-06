from __future__ import annotations

import base64

import keyring
from keyring.errors import KeyringError

from market_reporter.core.errors import SecretStorageError
from market_reporter.infra.security.crypto import generate_master_key


class KeychainStore:
    def __init__(self, service_name: str = "market-reporter", account: str = "master-key") -> None:
        self.service_name = service_name
        self.account = account

    def get_or_create_master_key(self) -> bytes:
        try:
            value = keyring.get_password(self.service_name, self.account)
        except KeyringError as exc:
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
            raise SecretStorageError(f"Failed to write master key into Keychain: {exc}") from exc
        return key
