"""Integration-тесты трекера откликов (applications)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Vacancy as VacancyORM
from tests.integration.auth_helpers import auth_headers, login

pytestmark = pytest.mark.asyncio


async def _setup_profile(client: AsyncClient, token: str) -> dict:
    return (
        await client.post(
            "/api/profiles",
            headers=auth_headers(token),
            json={"name": "Backend", "category": "it", "grade": "middle", "stack": ["python"]},
        )
    ).json()


async def _seed_vacancy(
    session: AsyncSession, *, external_id: str = "av-1", title: str = "Vacancy"
) -> VacancyORM:
    v = VacancyORM(
        external_id=external_id,
        source_type="hh",
        title=title,
        company_name="Acme",
        url=f"https://hh.ru/vacancy/{external_id}",
        published_at=datetime.now(UTC),
    )
    session.add(v)
    await session.commit()
    await session.refresh(v)
    return v


# ============================================================================
# Create
# ============================================================================


class TestCreateApplication:
    async def test_creates_with_default_status_sent(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        r = await client.post(
            f"/api/applications?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={
                "vacancy_id": vacancy.id,
                "cover_letter": "draft text",
                "notes": "первая встреча в среду",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "sent"
        assert body["cover_letter"] == "draft text"
        assert body["notes"] == "первая встреча в среду"

    async def test_history_has_sent_after_create(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/applications?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"vacancy_id": vacancy.id},
            )
        ).json()

        h = await client.get(
            f"/api/applications/{created['id']}/history", headers=auth_headers(token)
        )
        assert h.status_code == 200
        history = h.json()
        assert len(history) == 1
        assert history[0]["status"] == "sent"

    async def test_duplicate_returns_409_with_existing_id_header(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        first = await client.post(
            f"/api/applications?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={"vacancy_id": vacancy.id},
        )
        assert first.status_code == 201

        second = await client.post(
            f"/api/applications?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={"vacancy_id": vacancy.id},
        )
        assert second.status_code == 409
        assert second.headers["X-Existing-Application-Id"] == str(first.json()["id"])

    async def test_unknown_vacancy_404(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        r = await client.post(
            f"/api/applications?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={"vacancy_id": 99999},
        )
        assert r.status_code == 404

    async def test_other_user_profile_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        vacancy = await _seed_vacancy(db_session)

        token_b, _ = await login(client, telegram_id=2)
        r = await client.post(
            f"/api/applications?profile_id={profile_a['id']}",
            headers=auth_headers(token_b),
            json={"vacancy_id": vacancy.id},
        )
        assert r.status_code == 404


# ============================================================================
# List + Get
# ============================================================================


class TestListAndGet:
    async def test_list_empty_for_new_profile(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        r = await client.get(
            f"/api/profiles/{profile['id']}/applications", headers=auth_headers(token)
        )
        assert r.status_code == 200
        assert r.json() == []

    async def test_list_returns_newest_first(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)

        for i in range(3):
            v = await _seed_vacancy(db_session, external_id=f"v{i}")
            await client.post(
                f"/api/applications?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"vacancy_id": v.id},
            )

        r = await client.get(
            f"/api/profiles/{profile['id']}/applications", headers=auth_headers(token)
        )
        items = r.json()
        assert len(items) == 3
        # newest-first по id
        assert items[0]["id"] > items[1]["id"] > items[2]["id"]

    async def test_get_other_user_404(self, client: AsyncClient, db_session: AsyncSession) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/applications?profile_id={profile_a['id']}",
                headers=auth_headers(token_a),
                json={"vacancy_id": vacancy.id},
            )
        ).json()

        token_b, _ = await login(client, telegram_id=2)
        r = await client.get(f"/api/applications/{created['id']}", headers=auth_headers(token_b))
        assert r.status_code == 404


# ============================================================================
# Patch (statuses, notes, reminders)
# ============================================================================


class TestPatchApplication:
    async def test_patch_status_appends_history(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/applications?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"vacancy_id": vacancy.id},
            )
        ).json()

        # sent → hr → tech → offer
        for new_status in ("hr", "tech", "offer"):
            r = await client.patch(
                f"/api/applications/{created['id']}",
                headers=auth_headers(token),
                json={"status": new_status},
            )
            assert r.status_code == 200
            assert r.json()["status"] == new_status

        h = (
            await client.get(
                f"/api/applications/{created['id']}/history", headers=auth_headers(token)
            )
        ).json()
        statuses = [item["status"] for item in h]
        assert statuses == ["sent", "hr", "tech", "offer"]

    async def test_patch_same_status_doesnt_duplicate_history(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/applications?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"vacancy_id": vacancy.id},
            )
        ).json()

        # Меняем notes без status — history не должен расти
        await client.patch(
            f"/api/applications/{created['id']}",
            headers=auth_headers(token),
            json={"notes": "запомнил детали"},
        )
        # Снова устанавливаем status='sent' — то же значение, не должно писаться
        await client.patch(
            f"/api/applications/{created['id']}",
            headers=auth_headers(token),
            json={"status": "sent"},
        )

        h = (
            await client.get(
                f"/api/applications/{created['id']}/history", headers=auth_headers(token)
            )
        ).json()
        assert len(h) == 1
        assert h[0]["status"] == "sent"

    async def test_arbitrary_transitions_allowed(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """В v0.1 нет state-machine: sent → offer допустимо."""
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/applications?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"vacancy_id": vacancy.id},
            )
        ).json()

        # Скип всех промежуточных статусов
        r = await client.patch(
            f"/api/applications/{created['id']}",
            headers=auth_headers(token),
            json={"status": "offer"},
        )
        assert r.status_code == 200
        # И откат на reject
        r = await client.patch(
            f"/api/applications/{created['id']}",
            headers=auth_headers(token),
            json={"status": "reject"},
        )
        assert r.status_code == 200

    async def test_patch_reminder_only_stores_field(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/applications?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"vacancy_id": vacancy.id},
            )
        ).json()

        future = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        r = await client.patch(
            f"/api/applications/{created['id']}",
            headers=auth_headers(token),
            json={"next_reminder_at": future},
        )
        assert r.status_code == 200
        # Поле сохранилось (точное значение может отличаться из-за TZ-форматирования)
        assert r.json()["next_reminder_at"] is not None

    async def test_invalid_status_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/applications?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"vacancy_id": vacancy.id},
            )
        ).json()

        r = await client.patch(
            f"/api/applications/{created['id']}",
            headers=auth_headers(token),
            json={"status": "considering"},
        )
        assert r.status_code == 422

    async def test_patch_other_user_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/applications?profile_id={profile_a['id']}",
                headers=auth_headers(token_a),
                json={"vacancy_id": vacancy.id},
            )
        ).json()

        token_b, _ = await login(client, telegram_id=2)
        r = await client.patch(
            f"/api/applications/{created['id']}",
            headers=auth_headers(token_b),
            json={"status": "reject"},
        )
        assert r.status_code == 404


# ============================================================================
# Funnel
# ============================================================================


class TestFunnel:
    async def test_empty_funnel_zeros_everywhere(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        r = await client.get(f"/api/profiles/{profile['id']}/funnel", headers=auth_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["counts"] == {
            "sent": 0,
            "hr": 0,
            "tech": 0,
            "final": 0,
            "offer": 0,
            "reject": 0,
        }
        # rates все 0.0
        assert all(rate == 0.0 for rate in body["conversion_rates"].values())

    async def test_funnel_counts_by_current_status(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)

        # 4 applications: 2 sent, 1 hr, 1 offer
        for i in range(4):
            v = await _seed_vacancy(db_session, external_id=f"funnel-{i}")
            created = (
                await client.post(
                    f"/api/applications?profile_id={profile['id']}",
                    headers=auth_headers(token),
                    json={"vacancy_id": v.id},
                )
            ).json()
            if i == 0:
                await client.patch(
                    f"/api/applications/{created['id']}",
                    headers=auth_headers(token),
                    json={"status": "hr"},
                )
            elif i == 1:
                await client.patch(
                    f"/api/applications/{created['id']}",
                    headers=auth_headers(token),
                    json={"status": "offer"},
                )

        r = await client.get(f"/api/profiles/{profile['id']}/funnel", headers=auth_headers(token))
        body = r.json()
        assert body["total"] == 4
        assert body["counts"]["sent"] == 2
        assert body["counts"]["hr"] == 1
        assert body["counts"]["offer"] == 1
        assert body["counts"]["reject"] == 0
        # Conversion rate проверяем (50% sent, 25% hr, 25% offer)
        assert body["conversion_rates"]["sent"] == 0.5
        assert body["conversion_rates"]["hr"] == 0.25

    async def test_funnel_other_user_404(self, client: AsyncClient) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        token_b, _ = await login(client, telegram_id=2)
        r = await client.get(
            f"/api/profiles/{profile_a['id']}/funnel", headers=auth_headers(token_b)
        )
        assert r.status_code == 404


# ============================================================================
# Auth
# ============================================================================


class TestAuthRequired:
    async def test_list_without_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/profiles/1/applications")
        assert r.status_code == 401

    async def test_create_without_auth(self, client: AsyncClient) -> None:
        r = await client.post("/api/applications?profile_id=1", json={"vacancy_id": 1})
        assert r.status_code == 401

    async def test_funnel_without_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/profiles/1/funnel")
        assert r.status_code == 401
