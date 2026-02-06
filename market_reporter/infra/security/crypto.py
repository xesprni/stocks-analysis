from __future__ import annotations

import base64
import os
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def generate_master_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def encrypt_text(plaintext: str, key: bytes) -> Tuple[str, str]:
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(ciphertext).decode("utf-8"), base64.b64encode(nonce).decode("utf-8")


def decrypt_text(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    aes = AESGCM(key)
    ciphertext = base64.b64decode(ciphertext_b64.encode("utf-8"))
    nonce = base64.b64decode(nonce_b64.encode("utf-8"))
    plaintext = aes.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
