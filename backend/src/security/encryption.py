"""Envelope encryption для резюме (и любых других чувствительных полей).

Архитектура:

    ┌─ ENCRYPTION_KEY (env) ──────────────────────────────────┐
    │ KEK (Key Encryption Key) — 32 байта, единый для системы │
    └─────────────────────┬───────────────────────────────────┘
                          │ шифрует
                          ▼
    ┌─ users.dek_encrypted (BYTEA) ─────────────────────────┐
    │ DEK (Data Encryption Key) — 32 байта на каждого юзера │
    └─────────────────────┬─────────────────────────────────┘
                          │ шифрует
                          ▼
    ┌─ profiles.resume_encrypted (BYTEA) ──────────────────┐
    │ Резюме (cleartext UTF-8 → ciphertext)                │
    └──────────────────────────────────────────────────────┘

Зачем envelope:
- Ротация KEK не требует перешифровывать все резюме — только DEK'и (короткие).
- Можно отозвать доступ к юзеру удалением одного DEK без касания глобального ключа.
- Утечка БД без KEK = бесполезные шифротексты.

Формат шифротекста: nonce(12) || ciphertext_with_tag (формат AES-GCM из cryptography).
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.config import settings

_NONCE_SIZE = 12  # рекомендуется для GCM
_KEY_SIZE = 32  # AES-256


class EncryptionError(Exception):
    """Базовое исключение криптомодуля."""


class InvalidCiphertextError(EncryptionError):
    """Шифротекст повреждён, либо использован не тот ключ."""


class InvalidKeyError(EncryptionError):
    """KEK имеет неверную длину/формат."""


@lru_cache(maxsize=1)
def _kek() -> AESGCM:
    """Загружает KEK из ENCRYPTION_KEY и создаёт AES-GCM cipher. Кэшируется."""
    try:
        key = base64.b64decode(settings.encryption_key, validate=True)
    except Exception as exc:
        raise InvalidKeyError("ENCRYPTION_KEY must be valid base64-encoded 32 bytes") from exc
    if len(key) != _KEY_SIZE:
        raise InvalidKeyError(
            f"ENCRYPTION_KEY must decode to exactly {_KEY_SIZE} bytes, got {len(key)}"
        )
    return AESGCM(key)


def _encrypt(cipher: AESGCM, plaintext: bytes, aad: bytes | None = None) -> bytes:
    nonce = os.urandom(_NONCE_SIZE)
    ct = cipher.encrypt(nonce, plaintext, aad)
    return nonce + ct


def _decrypt(cipher: AESGCM, blob: bytes, aad: bytes | None = None) -> bytes:
    if len(blob) < _NONCE_SIZE + 16:  # nonce + хотя бы tag
        raise InvalidCiphertextError("blob too short to be valid AES-GCM ciphertext")
    nonce, ct = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
    try:
        return cipher.decrypt(nonce, ct, aad)
    except InvalidTag as exc:
        raise InvalidCiphertextError("AES-GCM authentication tag mismatch") from exc


# ============================================================================
# DEK lifecycle (per-user)
# ============================================================================
def generate_dek() -> bytes:
    """Генерирует новый случайный DEK (32 байта). Хранить в открытом виде нельзя."""
    return AESGCM.generate_key(bit_length=256)


def wrap_dek(dek: bytes) -> bytes:
    """Шифрует DEK через KEK. Результат пишется в `users.dek_encrypted`."""
    if len(dek) != _KEY_SIZE:
        raise InvalidKeyError(f"DEK must be exactly {_KEY_SIZE} bytes")
    return _encrypt(_kek(), dek)


def unwrap_dek(wrapped: bytes) -> bytes:
    """Расшифровывает DEK из БД через KEK."""
    return _decrypt(_kek(), wrapped)


# ============================================================================
# Field-level encryption (через DEK юзера)
# ============================================================================
def encrypt_field(dek: bytes, plaintext: str) -> bytes:
    """Шифрует строковое поле (например, резюме) через DEK юзера."""
    cipher = AESGCM(dek)
    return _encrypt(cipher, plaintext.encode("utf-8"))


def decrypt_field(dek: bytes, blob: bytes) -> str:
    """Расшифровывает поле, зашифрованное `encrypt_field` тем же DEK."""
    cipher = AESGCM(dek)
    return _decrypt(cipher, blob).decode("utf-8")


# ============================================================================
# Удобные комбинации (для частого пути «есть wrapped_dek и шифротекст»)
# ============================================================================
def encrypt_resume(wrapped_dek: bytes, resume_text: str) -> bytes:
    """Берёт DEK из wrapped формы, шифрует им резюме. Plaintext DEK не возвращает."""
    dek = unwrap_dek(wrapped_dek)
    try:
        return encrypt_field(dek, resume_text)
    finally:
        # cryptography сама не зануляет bytes (immutable), но избегаем
        # удержания DEK во фрейме после выхода.
        del dek


def decrypt_resume(wrapped_dek: bytes, resume_encrypted: bytes) -> str:
    """Обратное к encrypt_resume."""
    dek = unwrap_dek(wrapped_dek)
    try:
        return decrypt_field(dek, resume_encrypted)
    finally:
        del dek
