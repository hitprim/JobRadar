"""Структурированное логирование через loguru.

В dev — читаемый текст в stdout.
В prod — JSON в stdout (для Railway / Yandex Cloud log collection).

Чувствительные поля (резюме, текст сопроводительных, ПД) НИКОГДА не попадают в логи.
Если в `extra` появится одно из таких полей — оно будет заменено на "***".
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from loguru import logger

from src.config import settings

if TYPE_CHECKING:
    from loguru import Record

# Поля, которые НИКОГДА не должны попадать в логи в открытом виде.
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "resume_text",
        "resume",
        "resume_encrypted",
        "cover_letter",
        "letter",
        "letter_text",
        "first_name",
        "last_name",
        "username",
        "email",
        "phone",
        "dek",
        "dek_encrypted",
        "encryption_key",
        "jwt_secret",
        "bot_token",
        "openrouter_api_key",
        "db_password",
        "password",
        "token",
    }
)


def _scrub_sensitive(record: Record) -> bool:
    """Loguru-фильтр: маскирует чувствительные ключи в record['extra']."""
    extra = record.get("extra") or {}
    for key in list(extra.keys()):
        if key.lower() in _SENSITIVE_KEYS:
            extra[key] = "***"
    return True


def setup_logging() -> None:
    """Инициализация логгера. Вызывать один раз при старте приложения."""
    logger.remove()

    if settings.is_dev:
        logger.add(
            sys.stdout,
            level="DEBUG",
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
                "- <level>{message}</level> {extra}"
            ),
            filter=_scrub_sensitive,
            backtrace=True,
            diagnose=True,
        )
    else:
        logger.add(
            sys.stdout,
            level="INFO",
            serialize=True,  # JSON
            filter=_scrub_sensitive,
            backtrace=False,
            diagnose=False,
        )
