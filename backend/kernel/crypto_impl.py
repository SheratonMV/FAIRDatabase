"""
crypto_impl.py — AES-256-GCM encryption for FL gradient payloads.

Gradient updates are encrypted before transmission and decrypted in-memory on
the server. Raw gradient values are never persisted to disk.

This is core code (kernel). It may resolve the app ``SECRET_KEY`` itself, so a
plugin can call ``kernel.crypto.decrypt_weights(payload, task_id)`` without ever
handling the core secret (``kernel.env`` refuses ``SECRET_KEY`` to plugins).
Public surface is re-exported by ``kernel/crypto.py``.
"""
import os

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _resolve_secret(secret_key):
    """Return ``secret_key`` if given, else the Flask app's ``SECRET_KEY``.

    Lets kernel callers omit the secret entirely. Falls back to the env var
    when no app context is active (e.g. unit tests of the crypto layer). With
    neither available we raise: a built-in default key would be public, so
    anything encrypted under it would be readable by anyone.
    """
    if secret_key is not None:
        return secret_key
    try:
        from flask import current_app
        key = current_app.config["SECRET_KEY"]
    except Exception:
        key = os.environ.get("SECRET_KEY")
    if not key:
        raise RuntimeError(
            "No SECRET_KEY available for gradient encryption "
            "(no Flask app context and SECRET_KEY env var unset)."
        )
    return key


def _derive_task_key(task_id: str, secret_key: str) -> bytes:
    """Derive a 256-bit AES key from task_id + app SECRET_KEY using HKDF-SHA256."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"fl-gradient-encryption",
    )
    return hkdf.derive((secret_key + task_id).encode("utf-8"))


def encrypt_weights(weights: np.ndarray, task_id: str, secret_key: str = None) -> dict:
    """
    Encrypt a flat float32 weight array with AES-256-GCM.

    Returns a dict with hex-encoded 'ciphertext' and 'nonce'. A fresh random
    nonce is generated each call. ``secret_key`` defaults to the app SECRET_KEY.
    """
    key = _derive_task_key(task_id, _resolve_secret(secret_key))
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    plaintext = weights.astype(np.float32).tobytes()
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return {
        "ciphertext": ciphertext.hex(),
        "nonce": nonce.hex(),
    }


def decrypt_weights(payload: dict, task_id: str, secret_key: str = None) -> np.ndarray:
    """
    Decrypt a payload produced by encrypt_weights back to a float32 array.

    ``secret_key`` defaults to the app SECRET_KEY. Raises
    cryptography.exceptions.InvalidTag if the key or nonce is wrong.
    """
    key = _derive_task_key(task_id, _resolve_secret(secret_key))
    aesgcm = AESGCM(key)
    nonce = bytes.fromhex(payload["nonce"])
    ciphertext = bytes.fromhex(payload["ciphertext"])
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return np.frombuffer(plaintext, dtype=np.float32)
