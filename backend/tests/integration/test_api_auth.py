"""Integration-тесты POST /api/auth/telegram."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User as UserORM
from src.security.encryption import unwrap_dek
from src.security.jwt import decode_access_token
from tests.integration.auth_helpers import make_init_data

pytestmark = pytest.mark.asyncio


class TestTelegramLoginHappyPath:
    async def test_new_user_login_creates_record(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        init_data = make_init_data(telegram_id=111, first_name="Иван", username="ivan")
        response = await client.post("/api/auth/telegram", json={"init_data": init_data})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["is_new_user"] is True
        assert body["expires_in"] > 0
        assert body["user"]["telegram_id"] == 111
        assert body["user"]["first_name"] == "Иван"
        assert body["user"]["username"] == "ivan"
        assert body["user"]["active_profile_id"] is None
        assert body["user"]["credits"] == 0

        # Проверяем юзер реально создан в БД
        users = (await db_session.execute(select(UserORM))).scalars().all()
        assert len(users) == 1
        assert users[0].telegram_id == 111
        # И DEK действительно зашифрован (можно расшифровать KEK'ом)
        dek = unwrap_dek(users[0].dek_encrypted)
        assert len(dek) == 32

    async def test_jwt_contains_user_claims(self, client: AsyncClient) -> None:
        init_data = make_init_data(telegram_id=222, first_name="X")
        response = await client.post("/api/auth/telegram", json={"init_data": init_data})
        token = response.json()["access_token"]
        claims = decode_access_token(token)
        assert claims.telegram_id == 222
        assert claims.user_id > 0

    async def test_existing_user_login_is_idempotent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        init_data = make_init_data(telegram_id=333, first_name="A")
        first = await client.post("/api/auth/telegram", json={"init_data": init_data})
        assert first.json()["is_new_user"] is True

        # Второй логин — тот же юзер, не должен создавать новую запись
        init_data2 = make_init_data(telegram_id=333, first_name="A")
        second = await client.post("/api/auth/telegram", json={"init_data": init_data2})
        assert second.status_code == 200
        assert second.json()["is_new_user"] is False
        assert second.json()["user"]["id"] == first.json()["user"]["id"]

        users = (await db_session.execute(select(UserORM))).scalars().all()
        assert len(users) == 1

    async def test_existing_user_username_updated(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Первый логин со старым ником
        await client.post(
            "/api/auth/telegram",
            json={"init_data": make_init_data(telegram_id=444, username="old_nick")},
        )
        # Второй — с новым
        await client.post(
            "/api/auth/telegram",
            json={"init_data": make_init_data(telegram_id=444, username="new_nick")},
        )
        user = (
            await db_session.execute(select(UserORM).where(UserORM.telegram_id == 444))
        ).scalar_one()
        assert user.username == "new_nick"


class TestTelegramLoginRejection:
    async def test_invalid_signature_returns_401(self, client: AsyncClient) -> None:
        # Подменяем последний байт hash'а в валидном initData
        init_data = make_init_data(telegram_id=1)
        tampered = init_data[:-2] + ("00" if not init_data.endswith("00") else "ff")
        response = await client.post("/api/auth/telegram", json={"init_data": tampered})
        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()

    async def test_expired_returns_401(self, client: AsyncClient) -> None:
        old_auth_date = int(time.time()) - 86400 - 60  # старше 24ч
        init_data = make_init_data(telegram_id=1, auth_date=old_auth_date)
        response = await client.post("/api/auth/telegram", json={"init_data": init_data})
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    async def test_missing_init_data_returns_422(self, client: AsyncClient) -> None:
        # Pydantic validation — пустое тело
        response = await client.post("/api/auth/telegram", json={})
        assert response.status_code == 422

    async def test_empty_init_data_returns_422(self, client: AsyncClient) -> None:
        # min_length=1 в схеме
        response = await client.post("/api/auth/telegram", json={"init_data": ""})
        assert response.status_code == 422
