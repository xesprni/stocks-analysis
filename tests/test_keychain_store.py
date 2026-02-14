from __future__ import annotations

import base64

from keyring.errors import KeyringError

from market_reporter.infra.security.keychain_store import KeychainStore


def test_keychain_store_falls_back_to_file_when_keyring_read_fails(
    monkeypatch, tmp_path
) -> None:
    master_key_file = tmp_path / "master_key.b64"
    monkeypatch.setenv("MARKET_REPORTER_MASTER_KEY_FILE", str(master_key_file))

    def _raise_on_get_password(service_name: str, account: str) -> str:
        raise KeyringError("no backend")

    monkeypatch.setattr("keyring.get_password", _raise_on_get_password)

    store = KeychainStore()
    key_a = store.get_or_create_master_key()
    key_b = store.get_or_create_master_key()

    assert key_a == key_b
    assert master_key_file.exists()


def test_keychain_store_writes_file_when_keyring_write_fails(
    monkeypatch, tmp_path
) -> None:
    master_key_file = tmp_path / "master_key.b64"
    monkeypatch.setenv("MARKET_REPORTER_MASTER_KEY_FILE", str(master_key_file))

    def _none_on_get_password(service_name: str, account: str):
        return None

    def _raise_on_set_password(service_name: str, account: str, value: str) -> None:
        raise KeyringError("write failed")

    monkeypatch.setattr("keyring.get_password", _none_on_get_password)
    monkeypatch.setattr("keyring.set_password", _raise_on_set_password)

    store = KeychainStore()
    key = store.get_or_create_master_key()

    encoded = master_key_file.read_text(encoding="utf-8").strip()
    assert base64.b64decode(encoded.encode("utf-8")) == key
