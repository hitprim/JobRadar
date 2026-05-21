"""Хелперы для авторизации в integration-тестах."""

from __future__ import annotations

import time
from typing import Any

from httpx import AsyncClient

from src.config import settings
from src.security.telegram_auth import build_init_data_for_tests


def make_init_data(
    *,
    telegram_id: int = 100500,
    first_name: str = "Test",
    username: str | None = "tester",
    extra_user_fields: dict[str, Any] | None = None,
    auth_date: int | None = None,
) -> str:
    """Генерирует валидный initData для тестов."""
    user = {"id": telegram_id, "first_name": first_name}
    if username:
        user["username"] = username
    if extra_user_fields:
        user.update(extra_user_fields)
    return build_init_data_for_tests(
        bot_token=settings.bot_token,
        user=user,
        auth_date=auth_date if auth_date is not None else int(time.time()),
    )


async def login(client: AsyncClient, **kwargs: Any) -> tuple[str, dict[str, Any]]:
    """Делает POST /api/auth/telegram. Возвращает (token, user_dict)."""
    init_data = make_init_data(**kwargs)
    response = await client.post("/api/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 200, response.text
    data = response.json()
    return data["access_token"], data["user"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
