"""Integration-тесты шаблонов сопроводительных (letter_templates)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

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


_TPL = {"title": "Универсальное", "body": "Здравствуйте, {company}! Хочу на {position}."}


class TestCrud:
    async def test_create_and_list(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)

        r = await client.post(
            f"/api/profiles/{profile['id']}/letter-templates",
            headers=auth_headers(token),
            json=_TPL,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["title"] == _TPL["title"]
        assert body["body"] == _TPL["body"]

        lst = await client.get(
            f"/api/profiles/{profile['id']}/letter-templates", headers=auth_headers(token)
        )
        assert lst.status_code == 200
        assert len(lst.json()) == 1

    async def test_update(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        created = (
            await client.post(
                f"/api/profiles/{profile['id']}/letter-templates",
                headers=auth_headers(token),
                json=_TPL,
            )
        ).json()

        r = await client.patch(
            f"/api/letter-templates/{created['id']}",
            headers=auth_headers(token),
            json={"title": "Новый заголовок"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["title"] == "Новый заголовок"
        assert r.json()["body"] == _TPL["body"]  # тело не тронуто

    async def test_delete(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        created = (
            await client.post(
                f"/api/profiles/{profile['id']}/letter-templates",
                headers=auth_headers(token),
                json=_TPL,
            )
        ).json()

        r = await client.delete(
            f"/api/letter-templates/{created['id']}", headers=auth_headers(token)
        )
        assert r.status_code == 204
        lst = await client.get(
            f"/api/profiles/{profile['id']}/letter-templates", headers=auth_headers(token)
        )
        assert lst.json() == []


class TestValidation:
    async def test_empty_title_422(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        r = await client.post(
            f"/api/profiles/{profile['id']}/letter-templates",
            headers=auth_headers(token),
            json={"title": "", "body": "x"},
        )
        assert r.status_code == 422


class TestIsolation:
    async def test_foreign_profile_404(self, client: AsyncClient) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)

        token_b, _ = await login(client, telegram_id=2)
        # B пытается читать шаблоны профиля A.
        r = await client.get(
            f"/api/profiles/{profile_a['id']}/letter-templates",
            headers=auth_headers(token_b),
        )
        assert r.status_code == 404

    async def test_foreign_template_patch_404(self, client: AsyncClient) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        tpl = (
            await client.post(
                f"/api/profiles/{profile_a['id']}/letter-templates",
                headers=auth_headers(token_a),
                json=_TPL,
            )
        ).json()

        token_b, _ = await login(client, telegram_id=2)
        await _setup_profile(client, token_b)
        r = await client.patch(
            f"/api/letter-templates/{tpl['id']}",
            headers=auth_headers(token_b),
            json={"title": "hacked"},
        )
        assert r.status_code == 404


class TestAuthRequired:
    async def test_list_without_auth_401(self, client: AsyncClient) -> None:
        r = await client.get("/api/profiles/1/letter-templates")
        assert r.status_code == 401
