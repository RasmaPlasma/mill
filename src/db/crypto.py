"""AES-256-GCM encryption helpers for secrets and vault credentials.

The master key is read from the PLATFORM_MASTER_KEY environment variable
(hex-encoded 32-byte key). Every encrypt call generates a fresh 12-byte
random nonce so ciphertext is non-deterministic.

Wire format: nonce (12 bytes) ‖ tag (16 bytes) ‖ ciphertext
"""

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12  # 96 bits — standard for AES-GCM


def _get_key() -> bytes:
    hex_key = os.environ.get("PLATFORM_MASTER_KEY", "")
    if not hex_key:
        raise RuntimeError(
            "PLATFORM_MASTER_KEY environment variable is required for encryption. "
            "Generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    key = bytes.fromhex(hex_key)
    if len(key) != 32:
        raise ValueError(
            f"PLATFORM_MASTER_KEY must be 32 bytes (64 hex chars), got {len(key)} bytes"
        )
    return key


def encrypt(plaintext: str) -> bytes:
    """Encrypt plaintext string with AES-256-GCM.

    Returns:
        bytes: nonce (12) ‖ tag (16) ‖ ciphertext
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_SIZE)
    # associated_data is None — no additional authenticated data
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ct  # ct already includes the 16-byte tag appended


def decrypt(data: bytes) -> str:
    """Decrypt data produced by encrypt().

    Args:
        data: nonce (12) ‖ tag (16) ‖ ciphertext

    Returns:
        Decrypted plaintext string.

    Raises:
        cryptography.exceptions.InvalidTag: If the key is wrong or data is corrupted.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = data[:_NONCE_SIZE]
    ct_with_tag = data[_NONCE_SIZE:]
    plaintext = aesgcm.decrypt(nonce, ct_with_tag, None)
    return plaintext.decode("utf-8")
