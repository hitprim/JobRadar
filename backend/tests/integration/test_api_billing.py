"""Integration-тесты billing stub'а."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.auth_helpers import auth_headers, login

pytestmark = pytest.mark.asyncio


class TestBillingCredits:
    async def test_returns_seed_values(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        r = await client.get("/api/billing/credits", headers=auth_headers(token))
        assert r.status_code == 200, r.text
        body = r.json()
        # Из seed config (миграция 0001)
        assert body["beta_mode"] is True
        assert body["free_letters_per_month"] == 10
        assert body["free_scores_per_day"] == 50
        # Юзер только что создан — 0 кредитов
        assert body["credits"] == 0

    async def test_requires_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/billing/credits")
        assert r.status_code == 401
