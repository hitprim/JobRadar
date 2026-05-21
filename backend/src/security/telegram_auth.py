"""Валидация Telegram WebApp initData.

Спецификация: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Алгоритм:
1. initData — это URL-encoded query-строка вида
   `user=%7B...%7D&auth_date=1716000000&query_id=...&hash=abc...`
2. Парсим её, отделяем поле `hash`, остальные сортируем по ключу и формируем
   `data-check-string` = "<key1>=<value1>\\n<key2>=<value2>\\n...".
3. Считаем secret_key = HMAC_SHA256(key=b"WebAppData", msg=BOT_TOKEN).
4. Вычисляем computed_hash = HMAC_SHA256(key=secret_key, msg=data_check_string).
5. Сравниваем с `hash` из initData в constant-time.
6. Проверяем `auth_date` не старее `INIT_DATA_TTL_SECONDS` (защита от replay).

Возвращаем dict с распарсенными полями (user, query_id, auth_date, ...).
В user — словарь {id, first_name, last_name?, username?, ...}.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from src.config import settings


class InitDataError(Exception):
    """Базовое исключение валидации initData."""


class InvalidInitDataSignatureError(InitDataError):
    """HMAC не сошёлся — initData подделан или повреждён."""


class InitDataExpiredError(InitDataError):
    """auth_date старше TTL — потенциальный replay."""


class MalformedInitDataError(InitDataError):
    """Структура initData не соответствует спецификации Telegram."""


@dataclass(frozen=True)
class TelegramUser:
    """Поля пользователя из initData.user."""

    id: int
    first_name: str | None
    last_name: str | None
    username: str | None
    language_code: str | None
    is_premium: bool


@dataclass(frozen=True)
class ValidatedInitData:
    """Результат успешной валидации."""

    user: TelegramUser
    auth_date: int  # unix seconds
    query_id: str | None
    raw: dict[str, str]


def _build_secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def _compute_hash(secret_key: bytes, data_check_string: str) -> str:
    return hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()


def _parse_user(raw_user_json: str) -> TelegramUser:
    try:
        data = json.loads(raw_user_json)
    except json.JSONDecodeError as exc:
        raise MalformedInitDataError("'user' field is not valid JSON") from exc
    if not isinstance(data, dict) or "id" not in data:
        raise MalformedInitDataError("'user' field missing required 'id'")
    try:
        user_id = int(data["id"])
    except (TypeError, ValueError) as exc:
        raise MalformedInitDataError("'user.id' is not an integer") from exc
    return TelegramUser(
        id=user_id,
        first_name=_str_or_none(data.get("first_name")),
        last_name=_str_or_none(data.get("last_name")),
        username=_str_or_none(data.get("username")),
        language_code=_str_or_none(data.get("language_code")),
        is_premium=bool(data.get("is_premium", False)),
    )


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def validate_init_data(
    init_data: str,
    *,
    bot_token: str | None = None,
    ttl_seconds: int | None = None,
    now_ts: int | None = None,
) -> ValidatedInitData:
    """Валидирует Telegram WebApp initData.

    Args:
        init_data: URL-encoded query-строка от Telegram.WebApp.initData.
        bot_token: BOT_TOKEN. По умолчанию — из settings.
        ttl_seconds: Срок жизни auth_date. По умолчанию — из settings.
        now_ts: Текущее unix-время. Для тестов; в проде — int(time.time()).

    Raises:
        MalformedInitDataError: initData неполный/невалидный.
        InvalidInitDataSignatureError: HMAC не сошёлся.
        InitDataExpiredError: auth_date старше TTL.
    """
    if not init_data:
        raise MalformedInitDataError("init_data is empty")

    bot_token = bot_token or settings.bot_token
    ttl = ttl_seconds if ttl_seconds is not None else settings.init_data_ttl_seconds
    now = now_ts if now_ts is not None else int(time.time())

    # Парсим query-строку. keep_blank_values сохраняет пустые значения как ''.
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    raw: dict[str, str] = dict(pairs)
    if len(raw) != len(pairs):
        # дубликаты ключей — initData не должен их иметь
        raise MalformedInitDataError("duplicate keys in init_data")

    received_hash = raw.pop("hash", None)
    if not received_hash:
        raise MalformedInitDataError("missing 'hash' field")

    # data-check-string: <key>=<value>\n... в алфавитном порядке ключей
    data_check_string = "\n".join(f"{k}={raw[k]}" for k in sorted(raw))

    secret_key = _build_secret_key(bot_token)
    computed = _compute_hash(secret_key, data_check_string)

    if not hmac.compare_digest(computed, received_hash):
        raise InvalidInitDataSignatureError("HMAC mismatch")

    # auth_date обязателен по спецификации
    auth_date_raw = raw.get("auth_date")
    if not auth_date_raw:
        raise MalformedInitDataError("missing 'auth_date' field")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise MalformedInitDataError("'auth_date' is not an integer") from exc

    age = now - auth_date
    if age > ttl:
        raise InitDataExpiredError(f"auth_date is {age}s old (>{ttl}s TTL)")
    # Также защищаемся от слишком далёкого будущего (skew > 5 минут)
    if age < -300:
        raise InitDataExpiredError(f"auth_date is in the future ({-age}s)")

    # user обязателен для авторизации
    user_raw = raw.get("user")
    if not user_raw:
        raise MalformedInitDataError("missing 'user' field")
    user = _parse_user(user_raw)

    return ValidatedInitData(
        user=user,
        auth_date=auth_date,
        query_id=raw.get("query_id") or None,
        raw=raw,
    )


# ============================================================================
# Тестовая утилита: генерация валидного initData для unit/integration тестов.
# НЕ для использования в проде — это helper для контролируемой генерации.
# ============================================================================
def build_init_data_for_tests(
    *,
    bot_token: str,
    user: dict[str, Any],
    auth_date: int,
    query_id: str | None = "test_query_id",
    extra: dict[str, str] | None = None,
) -> str:
    """Генерирует валидный initData (с подписью).

    ВАЖНО: использовать только в тестах. В проде initData приходит от Telegram.
    """
    from urllib.parse import quote

    fields: dict[str, str] = {
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
        "auth_date": str(auth_date),
    }
    if query_id is not None:
        fields["query_id"] = query_id
    if extra:
        fields.update(extra)

    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = _build_secret_key(bot_token)
    hash_value = _compute_hash(secret_key, data_check_string)

    # Кодируем как настоящий initData от Telegram (URL-encoded values)
    parts = [f"{k}={quote(v, safe='')}" for k, v in fields.items()]
    parts.append(f"hash={hash_value}")
    return "&".join(parts)
