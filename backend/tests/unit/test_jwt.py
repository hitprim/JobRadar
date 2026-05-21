"""Unit-тесты JWT-обёртки."""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest

from src.config import settings
from src.security.jwt import (
    InvalidTokenError,
    decode_access_token,
    encode_access_token,
)


class TestRoundtrip:
    def test_encode_decode_basic(self) -> None:
        now = int(time.time())
        token = encode_access_token(user_id=42, telegram_id=123456789, ttl_minutes=60, now_ts=now)
        claims = decode_access_token(token)
        assert claims.user_id == 42
        assert claims.telegram_id == 123456789
        assert claims.issued_at == now
        assert claims.expires_at == now + 3600

    def test_token_is_three_parts(self) -> None:
        token = encode_access_token(user_id=1, telegram_id=1)
        assert token.count(".") == 2


class TestExpiration:
    def test_expired_token_rejected(self) -> None:
        # iat = now - 2h, ttl = 1h → exp в прошлом
        past = int(time.time()) - 7200
        token = encode_access_token(user_id=1, telegram_id=1, ttl_minutes=60, now_ts=past)
        with pytest.raises(InvalidTokenError, match="expired"):
            decode_access_token(token)

    def test_token_valid_before_expiration(self) -> None:
        # iat = now, ttl = 60min — заведомо валиден
        token = encode_access_token(user_id=1, telegram_id=1, ttl_minutes=60)
        claims = decode_access_token(token)
        assert claims.user_id == 1


class TestSignature:
    def test_tampered_signature_rejected(self) -> None:
        token = encode_access_token(user_id=1, telegram_id=1)
        # Меняем последний символ подписи
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(InvalidTokenError):
            decode_access_token(tampered)

    def test_garbage_rejected(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_access_token("not.a.jwt")

    def test_token_signed_with_other_secret_rejected(self) -> None:
        # Сами создаём JWT с чужим секретом
        payload = {
            "sub": "1",
            "tid": 1,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        foreign = pyjwt.encode(payload, "wrong-secret-key", algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_access_token(foreign)


class TestClaimsValidation:
    def test_missing_required_claim_rejected(self) -> None:
        # Создаём JWT с правильным секретом, но без tid
        payload = {
            "sub": "1",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token = pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_access_token(token)

    def test_non_integer_sub_rejected(self) -> None:
        payload = {
            "sub": "not_an_int",
            "tid": 1,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token = pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        with pytest.raises(InvalidTokenError, match="claims"):
            decode_access_token(token)
