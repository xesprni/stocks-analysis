from __future__ import annotations

import base64

from keyring.errors import KeyringError

from market_reporter.infra.security.crypto import (
    decrypt_text,
    encrypt_text,
    generate_master_key,
)
from market_reporter.infra.security.keychain_store import (
    KeychainStore,
    resolve_master_key_file,
)


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


def test_keychain_store_uses_db_adjacent_file_when_keyring_unavailable(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("MARKET_REPORTER_MASTER_KEY_FILE", raising=False)
    monkeypatch.delenv("MARKET_REPORTER_MASTER_KEY", raising=False)
    db_path = tmp_path / "data" / "market_reporter.db"
    database_url = f"sqlite:///{db_path}"

    def _raise_keyring_error(*args, **kwargs):
        raise KeyringError("no backend")

    monkeypatch.setattr("keyring.get_password", _raise_keyring_error)
    monkeypatch.setattr("keyring.set_password", _raise_keyring_error)

    file_path = resolve_master_key_file(database_url=database_url)
    store_a = KeychainStore(database_url=database_url)
    key_a = store_a.get_or_create_master_key()

    ciphertext, nonce = encrypt_text("linux-secret", key_a)

    store_b = KeychainStore(database_url=database_url)
    key_b = store_b.get_or_create_master_key()
    restored = decrypt_text(ciphertext, nonce, key_b)

    assert file_path == db_path.parent / "master_key.b64"
    assert file_path.exists()
    assert restored == "linux-secret"


def test_keychain_store_copies_keyring_value_to_file_backup(
    monkeypatch, tmp_path
) -> None:
    master_key_file = tmp_path / "master_key.b64"
    monkeypatch.setenv("MARKET_REPORTER_MASTER_KEY_FILE", str(master_key_file))
    expected = generate_master_key()
    encoded_expected = base64.b64encode(expected).decode("utf-8")

    def _keyring_get_password(service_name: str, account: str) -> str:
        return encoded_expected

    def _unexpected_keyring_set(service_name: str, account: str, value: str) -> None:
        raise AssertionError(
            "set_password should not be called when key already exists"
        )

    monkeypatch.setattr("keyring.get_password", _keyring_get_password)
    monkeypatch.setattr("keyring.set_password", _unexpected_keyring_set)

    store = KeychainStore()
    resolved = store.get_or_create_master_key()

    assert resolved == expected
    encoded = master_key_file.read_text(encoding="utf-8").strip()
    assert base64.b64decode(encoded.encode("utf-8")) == expected
