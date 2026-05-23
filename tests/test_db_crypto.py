"""Tests for db.crypto — AES-256-GCM encrypt/decrypt."""

import os

import pytest

# Ensure the env var is set before importing crypto
os.environ["PLATFORM_MASTER_KEY"] = "0" * 64

from db.crypto import decrypt, encrypt


class TestCrypto:
    def test_roundtrip_short(self):
        """Encrypt then decrypt returns the original plaintext."""
        plaintext = "hello world"
        ct = encrypt(plaintext)
        assert decrypt(ct) == plaintext

    def test_roundtrip_empty(self):
        """Empty string round-trips correctly."""
        ct = encrypt("")
        assert decrypt(ct) == ""

    def test_roundtrip_long(self):
        """Long plaintext round-trips correctly."""
        plaintext = "x" * 10_000
        ct = encrypt(plaintext)
        assert decrypt(ct) == plaintext

    def test_roundtrip_unicode(self):
        """Unicode plaintext round-trips correctly."""
        plaintext = "Hello 世界 🌍"
        ct = encrypt(plaintext)
        assert decrypt(ct) == plaintext

    def test_different_ciphertexts(self):
        """Two encryptions of the same plaintext produce different ciphertexts
        because each call generates a fresh random nonce."""
        ct1 = encrypt("same")
        ct2 = encrypt("same")
        assert ct1 != ct2

    def test_ciphertext_format(self):
        """Ciphertext is nonce (12) + tag (16) + payload."""
        ct = encrypt("test")
        # At minimum: 12-byte nonce + 16-byte tag + ciphertext
        assert len(ct) >= 12 + 16 + 1

    def test_wrong_key_raises(self):
        """Decrypting with a different key raises InvalidTag."""
        ct = encrypt("secret")
        # Swap the key
        old_key = os.environ["PLATFORM_MASTER_KEY"]
        os.environ["PLATFORM_MASTER_KEY"] = "f" * 64
        try:
            with pytest.raises(Exception):  # InvalidTag
                decrypt(ct)
        finally:
            os.environ["PLATFORM_MASTER_KEY"] = old_key

    def test_missing_key_raises(self):
        """encrypt() raises RuntimeError when PLATFORM_MASTER_KEY is empty."""
        old_key = os.environ.pop("PLATFORM_MASTER_KEY", None)
        os.environ["PLATFORM_MASTER_KEY"] = ""
        try:
            with pytest.raises(RuntimeError, match="PLATFORM_MASTER_KEY"):
                encrypt("test")
        finally:
            if old_key is not None:
                os.environ["PLATFORM_MASTER_KEY"] = old_key

    def test_wrong_key_length_raises(self):
        """PLATFORM_MASTER_KEY with wrong byte length raises ValueError."""
        old_key = os.environ.get("PLATFORM_MASTER_KEY")
        os.environ["PLATFORM_MASTER_KEY"] = "ab"  # 1 byte, not 32
        try:
            with pytest.raises(ValueError, match="32 bytes"):
                encrypt("test")
        finally:
            if old_key is not None:
                os.environ["PLATFORM_MASTER_KEY"] = old_key
