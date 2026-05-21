"""Unit-тесты валидации Telegram WebApp initData.

Проверяем корректность HMAC, защиту от replay, обработку искажений и подделок.
"""

from __future__ import annotations

import time

import pytest

from src.security.telegram_auth import (
    InitDataExpiredError,
    InvalidInitDataSignatureError,
    MalformedInitDataError,
    build_init_data_for_tests,
    validate_init_data,
)

# Тестовый bot_token (не настоящий, только для подписи в тестах).
TEST_BOT_TOKEN = "0000000000:AAAA-test-token-for-unit-tests-only"

USER_OBJ = {
    "id": 123456789,
    "first_name": "Иван",
    "last_name": "Петров",
    "username": "ivanp",
    "language_code": "ru",
    "is_premium": True,
}


def _now() -> int:
    return int(time.time())


class TestHappyPath:
    def test_valid_init_data_passes(self) -> None:
        now = _now()
        data = build_init_data_for_tests(bot_token=TEST_BOT_TOKEN, user=USER_OBJ, auth_date=now)
        result = validate_init_data(data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)
        assert result.user.id == 123456789
        assert result.user.first_name == "Иван"
        assert result.user.username == "ivanp"
        assert result.user.is_premium is True
        assert result.auth_date == now
        assert result.query_id == "test_query_id"

    def test_user_without_optional_fields(self) -> None:
        now = _now()
        data = build_init_data_for_tests(
            bot_token=TEST_BOT_TOKEN,
            user={"id": 1, "first_name": "X"},
            auth_date=now,
        )
        result = validate_init_data(data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)
        assert result.user.id == 1
        assert result.user.last_name is None
        assert result.user.username is None
        assert result.user.is_premium is False

    def test_extra_fields_dont_break_signature(self) -> None:
        # Telegram может добавлять новые поля в будущем — мы их сохраняем в raw
        now = _now()
        data = build_init_data_for_tests(
            bot_token=TEST_BOT_TOKEN,
            user={"id": 1, "first_name": "X"},
            auth_date=now,
            extra={"chat_type": "private", "chat_instance": "-987"},
        )
        result = validate_init_data(data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)
        assert result.raw["chat_type"] == "private"
        assert result.raw["chat_instance"] == "-987"


class TestSignature:
    def test_wrong_bot_token_rejected(self) -> None:
        now = _now()
        data = build_init_data_for_tests(bot_token=TEST_BOT_TOKEN, user=USER_OBJ, auth_date=now)
        with pytest.raises(InvalidInitDataSignatureError):
            validate_init_data(
                data,
                bot_token="9999999999:DIFFERENT-token",
                now_ts=now,
                ttl_seconds=86400,
            )

    def test_tampered_user_field_rejected(self) -> None:
        now = _now()
        data = build_init_data_for_tests(
            bot_token=TEST_BOT_TOKEN, user={"id": 1, "first_name": "X"}, auth_date=now
        )
        # Подменяем id в user — hash не пересчитан
        tampered = data.replace("%22id%22%3A1", "%22id%22%3A999")
        with pytest.raises(InvalidInitDataSignatureError):
            validate_init_data(tampered, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)

    def test_missing_hash_rejected(self) -> None:
        with pytest.raises(MalformedInitDataError, match="hash"):
            validate_init_data(
                "user=%7B%7D&auth_date=1716000000",
                bot_token=TEST_BOT_TOKEN,
                now_ts=_now(),
                ttl_seconds=86400,
            )

    def test_empty_init_data_rejected(self) -> None:
        with pytest.raises(MalformedInitDataError, match="empty"):
            validate_init_data("", bot_token=TEST_BOT_TOKEN, now_ts=_now(), ttl_seconds=86400)


class TestReplayProtection:
    def test_expired_auth_date_rejected(self) -> None:
        old = _now() - 86400 - 10  # старше 24ч на 10 секунд
        data = build_init_data_for_tests(bot_token=TEST_BOT_TOKEN, user=USER_OBJ, auth_date=old)
        with pytest.raises(InitDataExpiredError, match=">86400s TTL"):
            validate_init_data(data, bot_token=TEST_BOT_TOKEN, now_ts=_now(), ttl_seconds=86400)

    def test_just_within_ttl_passes(self) -> None:
        now = _now()
        old = now - 86400 + 5  # 23ч 59мин 55с — ещё в окне
        data = build_init_data_for_tests(bot_token=TEST_BOT_TOKEN, user=USER_OBJ, auth_date=old)
        result = validate_init_data(data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)
        assert result.auth_date == old

    def test_far_future_rejected(self) -> None:
        # Защита от clock skew > 5 минут
        now = _now()
        future = now + 600  # +10 минут
        data = build_init_data_for_tests(bot_token=TEST_BOT_TOKEN, user=USER_OBJ, auth_date=future)
        with pytest.raises(InitDataExpiredError, match="future"):
            validate_init_data(data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)

    def test_short_future_allowed(self) -> None:
        # Небольшой skew ОК (Telegram может опередить наш сервер на пару секунд)
        now = _now()
        future = now + 60  # +1 минута
        data = build_init_data_for_tests(bot_token=TEST_BOT_TOKEN, user=USER_OBJ, auth_date=future)
        result = validate_init_data(data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)
        assert result.auth_date == future


class TestMalformed:
    def test_missing_user_rejected(self) -> None:
        # auth_date есть, hash правильный, но user отсутствует
        from src.security.telegram_auth import _build_secret_key, _compute_hash

        now = _now()
        fields = {"auth_date": str(now)}
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        sk = _build_secret_key(TEST_BOT_TOKEN)
        h = _compute_hash(sk, data_check)
        init_data = f"auth_date={now}&hash={h}"
        with pytest.raises(MalformedInitDataError, match="user"):
            validate_init_data(init_data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)

    def test_user_with_invalid_json(self) -> None:
        from urllib.parse import quote

        from src.security.telegram_auth import _build_secret_key, _compute_hash

        now = _now()
        bad_user = "{not json"
        fields = {"user": bad_user, "auth_date": str(now)}
        data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
        sk = _build_secret_key(TEST_BOT_TOKEN)
        h = _compute_hash(sk, data_check)
        init_data = f"user={quote(bad_user, safe='')}&auth_date={now}&hash={h}"
        with pytest.raises(MalformedInitDataError, match="JSON"):
            validate_init_data(init_data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)

    def test_user_without_id(self) -> None:
        now = _now()
        data = build_init_data_for_tests(
            bot_token=TEST_BOT_TOKEN,
            user={"first_name": "X"},  # без id
            auth_date=now,
        )
        with pytest.raises(MalformedInitDataError, match="id"):
            validate_init_data(data, bot_token=TEST_BOT_TOKEN, now_ts=now, ttl_seconds=86400)

    def test_non_integer_auth_date(self) -> None:
        # Подменяем auth_date на нечисло, ломаем подпись — но первая ошибка
        # должна быть signature (hash сверяется до парсинга auth_date).
        # А вот если соберём заново с auth_date="not_int" — подпись валидна,
        # но парсинг упадёт на int()
        from urllib.parse import quote

        from src.security.telegram_auth import _build_secret_key, _compute_hash

        fields = {"user": '{"id":1}', "auth_date": "not_a_number"}
        data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
        sk = _build_secret_key(TEST_BOT_TOKEN)
        h = _compute_hash(sk, data_check)
        init_data = (
            f"user={quote(fields['user'], safe='')}&auth_date={fields['auth_date']}&hash={h}"
        )
        with pytest.raises(MalformedInitDataError, match="auth_date"):
            validate_init_data(
                init_data, bot_token=TEST_BOT_TOKEN, now_ts=_now(), ttl_seconds=86400
            )
