"""Integration-тесты CRUD профилей."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Profile as ProfileORM
from src.db.models import User as UserORM
from tests.integration.auth_helpers import auth_headers, login, make_init_data

pytestmark = pytest.mark.asyncio


# --- helpers ----------------------------------------------------------------


def _basic_profile_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Backend",
        "category": "it",
        "grade": "middle",
        "stack": ["python", "fastapi", "postgresql"],
        "salary_from": 200000,
        "salary_to": 350000,
        "work_format": ["remote", "hybrid"],
        "schedule": ["fullDay"],
        "area_ids": [1],
        "exclude_keywords": ["1с"],
    }
    payload.update(overrides)
    return payload


# --- list -------------------------------------------------------------------


class TestListProfiles:
    async def test_empty_for_new_user(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        r = await client.get("/api/profiles", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json() == []

    async def test_requires_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/profiles")
        assert r.status_code == 401

    async def test_invalid_token_rejected(self, client: AsyncClient) -> None:
        r = await client.get("/api/profiles", headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401


# --- create -----------------------------------------------------------------


class TestCreateProfile:
    async def test_create_basic_profile(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, user = await login(client)
        r = await client.post(
            "/api/profiles",
            headers=auth_headers(token),
            json=_basic_profile_payload(),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Backend"
        assert body["category"] == "it"
        assert body["grade"] == "middle"
        assert body["stack"] == ["python", "fastapi", "postgresql"]
        assert body["salary_from"] == 200000
        assert body["work_format"] == ["remote", "hybrid"]
        assert body["has_resume"] is False
        assert body["is_active"] is True

        # active_profile_id юзера обновился
        user_orm = await db_session.get(UserORM, user["id"])
        await db_session.refresh(user_orm)
        assert user_orm is not None
        assert user_orm.active_profile_id == body["id"]

    async def test_second_profile_returns_409(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        first = await client.post(
            "/api/profiles", headers=auth_headers(token), json=_basic_profile_payload()
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/profiles",
            headers=auth_headers(token),
            json=_basic_profile_payload(name="AI Engineer"),
        )
        assert second.status_code == 409
        assert "one active profile" in second.json()["detail"].lower()

    async def test_invalid_category_rejected(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        r = await client.post(
            "/api/profiles",
            headers=auth_headers(token),
            json=_basic_profile_payload(category="unknown"),
        )
        assert r.status_code == 422

    async def test_invalid_grade_rejected(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        r = await client.post(
            "/api/profiles",
            headers=auth_headers(token),
            json=_basic_profile_payload(grade="archmage"),
        )
        assert r.status_code == 422


# --- update -----------------------------------------------------------------


class TestUpdateProfile:
    async def test_patch_changes_fields(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        created = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token),
                json=_basic_profile_payload(),
            )
        ).json()

        r = await client.patch(
            f"/api/profiles/{created['id']}",
            headers=auth_headers(token),
            json={"salary_from": 250000, "stack": ["python", "django"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["salary_from"] == 250000
        assert body["stack"] == ["python", "django"]
        # Поле, которое мы не трогали, не должно потеряться
        assert body["name"] == "Backend"
        assert body["grade"] == "middle"

    async def test_patch_other_users_profile_returns_404(self, client: AsyncClient) -> None:
        # Юзер A создаёт профиль
        token_a, _ = await login(client, telegram_id=1)
        created = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token_a),
                json=_basic_profile_payload(),
            )
        ).json()

        # Юзер B пытается его обновить
        token_b, _ = await login(client, telegram_id=2)
        r = await client.patch(
            f"/api/profiles/{created['id']}",
            headers=auth_headers(token_b),
            json={"salary_from": 1},
        )
        assert r.status_code == 404


# --- soft-delete + activate --------------------------------------------------


class TestSoftDeleteAndActivate:
    async def test_delete_soft_deletes_and_resets_active(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, user = await login(client)
        created = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token),
                json=_basic_profile_payload(),
            )
        ).json()

        r = await client.delete(f"/api/profiles/{created['id']}", headers=auth_headers(token))
        assert r.status_code == 204

        # В БД is_active=false, профиль не пропал
        orm = await db_session.get(ProfileORM, created["id"])
        await db_session.refresh(orm)
        assert orm is not None
        assert orm.is_active is False

        # active_profile_id юзера сброшен
        user_orm = await db_session.get(UserORM, user["id"])
        await db_session.refresh(user_orm)
        assert user_orm is not None
        assert user_orm.active_profile_id is None

        # GET /api/profiles возвращает пустой список
        list_r = await client.get("/api/profiles", headers=auth_headers(token))
        assert list_r.json() == []

    async def test_can_recreate_profile_after_delete(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        first = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token),
                json=_basic_profile_payload(),
            )
        ).json()
        await client.delete(f"/api/profiles/{first['id']}", headers=auth_headers(token))

        # После soft-delete активных нет → можно создать новый
        second = await client.post(
            "/api/profiles",
            headers=auth_headers(token),
            json=_basic_profile_payload(name="AI"),
        )
        assert second.status_code == 201
        assert second.json()["name"] == "AI"
        assert second.json()["id"] != first["id"]


# --- resume ------------------------------------------------------------------


class TestResume:
    async def test_set_and_get_resume_roundtrip(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        created = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token),
                json=_basic_profile_payload(),
            )
        ).json()

        # Изначально резюме нет
        get0 = await client.get(
            f"/api/profiles/{created['id']}/resume", headers=auth_headers(token)
        )
        assert get0.status_code == 200
        assert get0.json() == {"resume_text": None}

        # Загружаем
        resume = "Senior Backend. Python, asyncio, PostgreSQL. 5 лет опыта. 🚀"
        put = await client.put(
            f"/api/profiles/{created['id']}/resume",
            headers=auth_headers(token),
            json={"resume_text": resume},
        )
        assert put.status_code == 204

        # Читаем — расшифровка идёт корректно
        get1 = await client.get(
            f"/api/profiles/{created['id']}/resume", headers=auth_headers(token)
        )
        assert get1.json()["resume_text"] == resume

        # has_resume теперь true в /profiles
        list_r = await client.get("/api/profiles", headers=auth_headers(token))
        assert list_r.json()[0]["has_resume"] is True

    async def test_resume_too_long_returns_413(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        created = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token),
                json=_basic_profile_payload(),
            )
        ).json()
        # Pydantic schema валидация (max_length=100_000) → 422
        # Бизнес-лимит в сервисе совпадает, поэтому frontend упрётся в 422 раньше
        r = await client.put(
            f"/api/profiles/{created['id']}/resume",
            headers=auth_headers(token),
            json={"resume_text": "x" * 100_001},
        )
        assert r.status_code == 422

    async def test_other_user_cannot_read_resume(self, client: AsyncClient) -> None:
        # A создаёт профиль и резюме
        token_a, _ = await login(client, telegram_id=1)
        created = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token_a),
                json=_basic_profile_payload(),
            )
        ).json()
        await client.put(
            f"/api/profiles/{created['id']}/resume",
            headers=auth_headers(token_a),
            json={"resume_text": "secret"},
        )

        # B пытается прочитать — 404
        token_b, _ = await login(client, telegram_id=2)
        r = await client.get(f"/api/profiles/{created['id']}/resume", headers=auth_headers(token_b))
        assert r.status_code == 404


# --- auth security across profiles -----------------------------------------


class TestAuthIsolation:
    async def test_user_a_cannot_see_user_b_profiles(self, client: AsyncClient) -> None:
        token_a, _ = await login(client, telegram_id=1)
        await client.post(
            "/api/profiles",
            headers=auth_headers(token_a),
            json=_basic_profile_payload(name="A's profile"),
        )

        token_b, _ = await login(client, telegram_id=2)
        r = await client.get("/api/profiles", headers=auth_headers(token_b))
        assert r.status_code == 200
        assert r.json() == []

    async def test_bogus_init_data_rejected_at_login(self, client: AsyncClient) -> None:
        # Сборка initData с чужим bot_token (не нашим)
        import time as _time

        from src.security.telegram_auth import build_init_data_for_tests

        bogus = build_init_data_for_tests(
            bot_token="9999999999:WRONG-token",
            user={"id": 1, "first_name": "Bad"},
            auth_date=int(_time.time()),
        )
        r = await client.post("/api/auth/telegram", json={"init_data": bogus})
        assert r.status_code == 401

    async def test_login_then_use_token_works_end_to_end(self, client: AsyncClient) -> None:
        # Полный flow: login → create profile → activate
        token, _ = await login(client, telegram_id=42)
        profile = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token),
                json=_basic_profile_payload(),
            )
        ).json()
        # soft-delete → активный сбрасывается
        await client.delete(f"/api/profiles/{profile['id']}", headers=auth_headers(token))
        # Создаём новый и активируем явно (на самом деле он уже активный после
        # create, но проверим что endpoint работает)
        new_profile = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token),
                json=_basic_profile_payload(name="Second"),
            )
        ).json()
        r = await client.post(
            f"/api/profiles/{new_profile['id']}/activate", headers=auth_headers(token)
        )
        assert r.status_code == 204

    async def test_init_data_with_extra_init_data(self, client: AsyncClient) -> None:
        """Smoke: что make_init_data импортируется и используется чисто."""
        init_data = make_init_data(telegram_id=999)
        r = await client.post("/api/auth/telegram", json={"init_data": init_data})
        assert r.status_code == 200
