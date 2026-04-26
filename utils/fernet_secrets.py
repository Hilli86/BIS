"""Verschlüsselung sensibler Felder (z. B. MQTT-Passwort) mit SECRET_KEY-abgeleitetem Fernet-Schlüssel."""

from __future__ import annotations

import base64
import hashlib


def _fernet_key_from_secret(secret: str | None) -> bytes:
    if not secret:
        raise ValueError('SECRET_KEY fehlt')
    digest = hashlib.sha256(secret.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_text(plain: str | None, secret_key: str | None) -> str | None:
    if plain is None or plain == '':
        return None
    from cryptography.fernet import Fernet
    f = Fernet(_fernet_key_from_secret(secret_key))
    return f.encrypt(plain.encode('utf-8')).decode('ascii')


def decrypt_text(token: str | None, secret_key: str | None) -> str | None:
    if not token:
        return None
    from cryptography.fernet import Fernet
    f = Fernet(_fernet_key_from_secret(secret_key))
    try:
        return f.decrypt(token.encode('ascii')).decode('utf-8')
    except Exception:
        return None
