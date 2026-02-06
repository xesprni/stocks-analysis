import unittest

from market_reporter.infra.security.crypto import decrypt_text, encrypt_text, generate_master_key


class CryptoTest(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        key = generate_master_key()
        plaintext = "sk-test-123456"

        ciphertext, nonce = encrypt_text(plaintext, key)
        restored = decrypt_text(ciphertext, nonce, key)

        self.assertEqual(restored, plaintext)


if __name__ == "__main__":
    unittest.main()
