"""JWT для аутентификации API-запросов.

В каждом access-токене:
- sub (string)      — user_id (наш внутренний id из users.id)
- tid (int)         — telegram_id (для логов и удобства)
- exp (int)         — unix-время истечения
- iat (int)         — unix-время выдачи

Алгоритм — HS256 с jwt_secret из settings. TTL — jwt_ttl_minutes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt as pyjwt

from src.config import settings


class JWTError(Exception):
    """Базовое исключение JWT-модуля."""


class InvalidTokenError(JWTError):
    """Подпись неверна, токен повреждён, или истёк."""


@dataclass(frozen=True)
class TokenClaims:
    """Полезная нагрузка JWT после успешной валидации."""

    user_id: int
    telegram_id: int
    issued_at: int
    expires_at: int


def encode_access_token(
    *,
    user_id: int,
    telegram_id: int,
    ttl_minutes: int | None = None,
    now_ts: int | None = None,
) -> str:
    """Создаёт подписанный JWT для юзера."""
    now = now_ts if now_ts is not None else int(time.time())
    ttl = ttl_minutes if ttl_minutes is not None else settings.jwt_ttl_minutes
    payload = {
        "sub": str(user_id),  # JWT стандарт: sub — строка
        "tid": telegram_id,
        "iat": now,
        "exp": now + ttl * 60,
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenClaims:
    """Декодирует и валидирует JWT.

    Raises:
        InvalidTokenError: подпись не сошлась, или токен истёк/повреждён.
    """
    try:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "tid", "iat", "exp"]},
        )
    except pyjwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("token expired") from exc
    except pyjwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"invalid token: {exc}") from exc

    try:
        user_id = int(payload["sub"])
        telegram_id = int(payload["tid"])
        iat = int(payload["iat"])
        exp = int(payload["exp"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidTokenError("invalid claims structure") from exc

    return TokenClaims(
        user_id=user_id,
        telegram_id=telegram_id,
        issued_at=iat,
        expires_at=exp,
    )
