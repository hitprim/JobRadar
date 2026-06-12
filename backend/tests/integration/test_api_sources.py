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


class _FakeBot:
    """Мок aiogram.Bot — глотает send_message без сети."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None) -> None:  # noqa: ANN001
        self.sent.append({"chat_id": chat_id, "text": text})

    class _Session:
        async def close(self) -> None: ...

    @property
    def session(self) -> _Session:
        return _FakeBot._Session()


class TestRefreshSource:
    async def test_refresh_starts_background_parse(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Refresh теперь async: 202 сразу, парсинг + пуш — в фоне.

        Под ASGITransport background task успевает отработать до возврата ответа,
        поэтому после POST данные уже в БД. Source-impl и Bot мокаем.
        """
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
        from src.services.notifications import NotificationsService

        monkeypatch.setattr(parser_module, "get_source_impl", lambda _: _MockSource())
        fake_bot = _FakeBot()
        monkeypatch.setattr(NotificationsService, "_build_bot", lambda self: fake_bot)

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
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["source_id"] == created["id"]
        assert body["status"] == "started"

        # Фоновая задача отработала: источник в статусе ok, юзеру ушёл пуш.
        sources = (
            await client.get(
                f"/api/profiles/{profile['id']}/sources", headers=auth_headers(token)
            )
        ).json()
        assert sources[0]["last_status"] == "ok"
        assert sources[0]["vacancies_today"] == 2
        assert len(fake_bot.sent) == 1
        assert "2" in fake_bot.sent[0]["text"]

    async def test_refresh_unknown_source_404(
        self, client: AsyncClient
    ) -> None:
        token, _ = await login(client)
        r = await client.post("/api/sources/999999/refresh", headers=auth_headers(token))
        assert r.status_code == 404
