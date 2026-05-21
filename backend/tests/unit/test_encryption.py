"""Unit-тесты envelope encryption (KEK + per-user DEK).

Эти тесты — фундамент безопасности резюме. Падают → откатываем релиз.
"""

from __future__ import annotations

import base64
import os

import pytest

from src.security import encryption
from src.security.encryption import (
    InvalidCiphertextError,
    InvalidKeyError,
    decrypt_field,
    decrypt_resume,
    encrypt_field,
    encrypt_resume,
    generate_dek,
    unwrap_dek,
    wrap_dek,
)


class TestDEKLifecycle:
    def test_generate_dek_returns_32_bytes(self) -> None:
        dek = generate_dek()
        assert isinstance(dek, bytes)
        assert len(dek) == 32

    def test_generate_dek_unique(self) -> None:
        # Очень маловероятно совпадение криптостойких случайных 32 байт.
        deks = {generate_dek() for _ in range(100)}
        assert len(deks) == 100

    def test_wrap_unwrap_roundtrip(self) -> None:
        dek = generate_dek()
        wrapped = wrap_dek(dek)
        assert dek == unwrap_dek(wrapped)

    def test_wrap_includes_nonce_and_tag(self) -> None:
        # 12 байт nonce + 32 байта DEK + 16 байт GCM tag = 60 байт
        dek = generate_dek()
        assert len(wrap_dek(dek)) == 60

    def test_wrap_produces_different_ciphertext_each_call(self) -> None:
        # Случайный nonce → разный шифротекст для одного и того же DEK.
        dek = generate_dek()
        assert wrap_dek(dek) != wrap_dek(dek)

    def test_wrap_rejects_wrong_size_dek(self) -> None:
        with pytest.raises(InvalidKeyError):
            wrap_dek(b"too_short")
        with pytest.raises(InvalidKeyError):
            wrap_dek(b"x" * 31)
        with pytest.raises(InvalidKeyError):
            wrap_dek(b"x" * 33)

    def test_unwrap_rejects_tampered_ciphertext(self) -> None:
        dek = generate_dek()
        wrapped = bytearray(wrap_dek(dek))
        wrapped[-1] ^= 0xFF  # портим последний байт (GCM tag)
        with pytest.raises(InvalidCiphertextError):
            unwrap_dek(bytes(wrapped))

    def test_unwrap_rejects_too_short_blob(self) -> None:
        with pytest.raises(InvalidCiphertextError):
            unwrap_dek(b"too_short")
        with pytest.raises(InvalidCiphertextError):
            unwrap_dek(b"")


class TestFieldEncryption:
    def test_field_roundtrip_ascii(self) -> None:
        dek = generate_dek()
        ct = encrypt_field(dek, "Hello, world!")
        assert decrypt_field(dek, ct) == "Hello, world!"

    def test_field_roundtrip_cyrillic(self) -> None:
        dek = generate_dek()
        text = "Резюме: Python, FastAPI, PostgreSQL. 5 лет опыта. 中文 إيموجي 🚀"
        ct = encrypt_field(dek, text)
        assert decrypt_field(dek, ct) == text

    def test_field_roundtrip_empty_string(self) -> None:
        dek = generate_dek()
        ct = encrypt_field(dek, "")
        assert decrypt_field(dek, ct) == ""

    def test_field_roundtrip_large_payload(self) -> None:
        dek = generate_dek()
        # ~50 KB резюме — реалистичный потолок
        text = "x" * 50_000
        ct = encrypt_field(dek, text)
        assert decrypt_field(dek, ct) == text

    def test_field_rejects_wrong_dek(self) -> None:
        dek1 = generate_dek()
        dek2 = generate_dek()
        ct = encrypt_field(dek1, "secret")
        with pytest.raises(InvalidCiphertextError):
            decrypt_field(dek2, ct)

    def test_field_rejects_tampered_ciphertext(self) -> None:
        dek = generate_dek()
        ct = bytearray(encrypt_field(dek, "secret"))
        ct[len(ct) // 2] ^= 0xFF
        with pytest.raises(InvalidCiphertextError):
            decrypt_field(dek, bytes(ct))


class TestResumeHelpers:
    def test_resume_roundtrip_via_wrapped_dek(self) -> None:
        dek = generate_dek()
        wrapped = wrap_dek(dek)
        resume = "Я Backend-разработчик с 5 годами опыта на Python."
        ct = encrypt_resume(wrapped, resume)
        assert decrypt_resume(wrapped, ct) == resume


class TestKEKValidation:
    def _reset_kek_cache(self) -> None:
        """KEK кэшируется через lru_cache — сбрасываем между тестами."""
        encryption._kek.cache_clear()

    def test_kek_loaded_from_env(self) -> None:
        # Базовая проверка: KEK из текущего окружения валиден.
        self._reset_kek_cache()
        encryption._kek()  # не должно бросить

    def test_invalid_base64_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._reset_kek_cache()
        monkeypatch.setattr(encryption.settings, "encryption_key", "not-valid-base64!!!")
        with pytest.raises(InvalidKeyError, match="base64"):
            encryption._kek()
        self._reset_kek_cache()

    def test_wrong_length_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._reset_kek_cache()
        short_key = base64.b64encode(os.urandom(16)).decode()  # только 16 байт
        monkeypatch.setattr(encryption.settings, "encryption_key", short_key)
        with pytest.raises(InvalidKeyError, match="32 bytes"):
            encryption._kek()
        self._reset_kek_cache()
