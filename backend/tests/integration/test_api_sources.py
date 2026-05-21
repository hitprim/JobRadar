"""Integration-тесты sources CRUD + refresh (с мок-Source через monkeypatch)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from src.domain.vacancy import ParsedVacancy
from tests.integration.auth_helpers import auth_headers, login

pytestmark = pytest.mark.asyncio


async def _create_profile(client: AsyncClient, token: str) -> dict:
    r = await client.post(
        "/api/profiles",
        headers=auth_headers(token),
        json={
            "name": "Backend",
            "category": "it",
            "grade": "middle",
            "stack": ["python", "fastapi"],
            "area_ids": [1],
        },
    )
    assert r.status_code == 201
    return r.json()


class TestSourcesCrud:
    async def test_list_empty_for_new_profile(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _create_profile(client, token)
        r = await client.get(f"/api/profiles/{profile['id']}/sources", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json() == []

    async def test_create_hh_source(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _create_profile(client, token)
        r = await client.post(
            f"/api/profiles/{profile['id']}/sources",
            headers=auth_headers(token),
            json={"type": "hh", "search_params": {"period": 14}},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["type"] == "hh"
        assert body["is_active"] is True
        assert body["search_params"] == {"period": 14}
        assert body["vacancies_today"] == 0

    async def test_create_non_hh_rejected_in_v01(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _create_profile(client, token)
        r = await client.post(
            f"/api/profiles/{profile['id']}/sources",
            headers=auth_headers(token),
            json={"type": "habr"},
        )
        assert r.status_code == 400

    async def test_invalid_type_rejected_by_schema(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _create_profile(client, token)
        r = await client.post(
            f"/api/profiles/{profile['id']}/sources",
            headers=auth_headers(token),
            json={"type": "bogus"},
        )
        assert r.status_code == 422

    async def test_other_user_cannot_list_or_create(self, client: AsyncClient) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _create_profile(client, token_a)

        token_b, _ = await login(client, telegram_id=2)
        r = await client.get(
            f"/api/profiles/{profile_a['id']}/sources", headers=auth_headers(token_b)
        )
        assert r.status_code == 404
        r = await client.post(
            f"/api/profiles/{profile_a['id']}/sources",
            headers=auth_headers(token_b),
            json={"type": "hh"},
        )
        assert r.status_code == 404

    async def test_delete_source(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _create_profile(client, token)
        created = (
            await client.post(
                f"/api/profiles/{profile['id']}/sources",
                headers=auth_headers(token),
                json={"type": "hh"},
            )
        ).json()
        r = await client.delete(f"/api/sources/{created['id']}", headers=auth_headers(token))
        assert r.status_code == 204
        # Уже удалён → 404
        r = await client.delete(f"/api/sources/{created['id']}", headers=auth_headers(token))
        assert r.status_code == 404

    async def test_other_user_cannot_delete(self, client: AsyncClient) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _create_profile(client, token_a)
        created = (
            await client.post(
                f"/api/profiles/{profile_a['id']}/sources",
                headers=auth_headers(token_a),
                json={"type": "hh"},
            )
        ).json()
        token_b, _ = await login(client, telegram_id=2)
        r = await client.delete(f"/api/sources/{created['id']}", headers=auth_headers(token_b))
        assert r.status_code == 404


class TestRefreshSource:
    async def test_refresh_with_mock_source(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Подменяем фабрику get_source_impl на mock, возвращающий 2 ParsedVacancy.

        Так избегаем сетевых вызовов к hh.ru.
        """
        # Mock-Source
        from src.sources.base import Source as SourceImpl

        class _MockSource(SourceImpl):
            source_type = "hh"

            async def fetch(self, profile, search_params=None):  # type: ignore[override]
                return [
                    ParsedVacancy(
                        external_id="ext-1",
                        source_type="hh",
                        title="Python Dev",
                        company_name="Acme",
                        salary_from=200000,
                    ),
                    ParsedVacancy(
                        external_id="ext-2",
                        source_type="hh",
                        title="Backend Engineer",
                    ),
                ]

        import src.services.parser as parser_module

        monkeypatch.setattr(parser_module, "get_source_impl", lambda _: _MockSource())

        # Полный flow: login → profile → source → refresh
        token, _ = await login(client)
        profile = await _create_profile(client, token)
        created = (
            await client.post(
                f"/api/profiles/{profile['id']}/sources",
                headers=auth_headers(token),
                json={"type": "hh"},
            )
        ).json()

        r = await client.post(f"/api/sources/{created['id']}/refresh", headers=auth_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fetched"] == 2
        assert body["inserted"] == 2
        assert body["updated"] == 0
        assert body["status"] == "ok"

        # Повторный refresh — все 2 уже в БД, должны быть updated
        r = await client.post(f"/api/sources/{created['id']}/refresh", headers=auth_headers(token))
        body = r.json()
        assert body["fetched"] == 2
        assert body["inserted"] == 0
        assert body["updated"] == 2
        assert body["status"] == "ok"
