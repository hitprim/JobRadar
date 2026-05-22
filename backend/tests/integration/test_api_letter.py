"""Integration-тесты letters API."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Vacancy as VacancyORM
from src.llm import get_llm_provider
from src.main import app
from tests.integration.auth_helpers import auth_headers, login
from tests.integration.mocks import MockLLMProvider, good_letter_response

pytestmark = pytest.mark.asyncio


async def _setup_profile(client: AsyncClient, token: str) -> dict:
    return (
        await client.post(
            "/api/profiles",
            headers=auth_headers(token),
            json={
                "name": "Backend",
                "category": "it",
                "grade": "middle",
                "stack": ["python", "fastapi"],
                "salary_from": 200000,
            },
        )
    ).json()


async def _seed_vacancy(session: AsyncSession, **kwargs) -> VacancyORM:
    defaults: dict = {
        "external_id": "lvac-1",
        "source_type": "hh",
        "title": "Senior Python",
        "company_name": "Acme",
        "salary_from": 300000,
        "salary_currency": "RUR",
        "url": "https://hh.ru/vacancy/lvac-1",
        "area_name": "Москва",
        "description": "Backend на Python и FastAPI. Микросервисы.",
        "key_skills": ["python", "fastapi"],
        "published_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    v = VacancyORM(**defaults)
    session.add(v)
    await session.commit()
    await session.refresh(v)
    return v


def _use_mock_llm(mock: MockLLMProvider) -> None:
    app.dependency_overrides[get_llm_provider] = lambda: mock


@pytest.fixture(autouse=True)
def _reset_llm_override():
    yield
    app.dependency_overrides.pop(get_llm_provider, None)


class TestGenerateLetter:
    async def test_generates_and_persists(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mock = MockLLMProvider(response=good_letter_response())
        _use_mock_llm(mock)

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        r = await client.post(
            f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["letter"]["text"].startswith("Здравствуйте")
        assert body["letter"]["used_in_application"] is False
        assert body["letter"]["prompt_used"] == "letters/it.md"
        assert len(body["draft_notes"]) >= 1
        assert mock.call_count == 1

    async def test_each_call_creates_new_record(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mock = MockLLMProvider(
            responses=[
                good_letter_response(letter_text="Письмо номер один. " * 20),
                good_letter_response(letter_text="Письмо номер два, другой стиль. " * 12),
            ]
        )
        _use_mock_llm(mock)

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        r1 = await client.post(
            f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={},
        )
        r2 = await client.post(
            f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={},
        )
        assert r1.json()["letter"]["id"] != r2.json()["letter"]["id"]
        assert mock.call_count == 2

    async def test_extra_instructions_in_user_message(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mock = MockLLMProvider(response=good_letter_response())
        _use_mock_llm(mock)

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        await client.post(
            f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={"extra_instructions": "UNIQUE-MARKER-XYZ упомяни мой K8s"},
        )
        assert "UNIQUE-MARKER-XYZ" in mock.last_user_message()
        # И в правильном теге
        assert "<extra_instructions>" in mock.last_user_message()

    async def test_extra_instructions_too_long_413(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _use_mock_llm(MockLLMProvider(response=good_letter_response()))
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        r = await client.post(
            f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={"extra_instructions": "x" * 2001},
        )
        # 422 от pydantic max_length=2000 в схеме
        assert r.status_code == 422

    async def test_unknown_vacancy_404(self, client: AsyncClient) -> None:
        _use_mock_llm(MockLLMProvider(response=good_letter_response()))
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        r = await client.post(
            f"/api/vacancies/99999/letter?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={},
        )
        assert r.status_code == 404

    async def test_other_user_profile_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _use_mock_llm(MockLLMProvider(response=good_letter_response()))

        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        vacancy = await _seed_vacancy(db_session)

        token_b, _ = await login(client, telegram_id=2)
        r = await client.post(
            f"/api/vacancies/{vacancy.id}/letter?profile_id={profile_a['id']}",
            headers=auth_headers(token_b),
            json={},
        )
        assert r.status_code == 404

    async def test_llm_error_502(self, client: AsyncClient, db_session: AsyncSession) -> None:
        from src.llm.base import LLMProvider, LLMUnavailableError

        class _FailLLM(LLMProvider):
            async def complete(self, *, system, user, response_schema):  # type: ignore[override]
                raise LLMUnavailableError("simulated down")

        app.dependency_overrides[get_llm_provider] = lambda: _FailLLM()

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        r = await client.post(
            f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={},
        )
        assert r.status_code == 502


class TestGetAndPatchLetter:
    async def test_get_own_letter(self, client: AsyncClient, db_session: AsyncSession) -> None:
        _use_mock_llm(MockLLMProvider(response=good_letter_response()))
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        created = (
            await client.post(
                f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={},
            )
        ).json()["letter"]

        r = await client.get(f"/api/letters/{created['id']}", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    async def test_get_others_letter_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _use_mock_llm(MockLLMProvider(response=good_letter_response()))

        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/vacancies/{vacancy.id}/letter?profile_id={profile_a['id']}",
                headers=auth_headers(token_a),
                json={},
            )
        ).json()["letter"]

        token_b, _ = await login(client, telegram_id=2)
        r = await client.get(f"/api/letters/{created['id']}", headers=auth_headers(token_b))
        assert r.status_code == 404

    async def test_patch_text_and_used_flag(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _use_mock_llm(MockLLMProvider(response=good_letter_response()))
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={},
            )
        ).json()["letter"]

        edited = "Моя отредактированная версия письма."
        r = await client.patch(
            f"/api/letters/{created['id']}",
            headers=auth_headers(token),
            json={"text": edited, "used_in_application": True},
        )
        assert r.status_code == 200
        assert r.json()["text"] == edited
        assert r.json()["used_in_application"] is True

    async def test_patch_others_letter_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _use_mock_llm(MockLLMProvider(response=good_letter_response()))

        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        vacancy = await _seed_vacancy(db_session)
        created = (
            await client.post(
                f"/api/vacancies/{vacancy.id}/letter?profile_id={profile_a['id']}",
                headers=auth_headers(token_a),
                json={},
            )
        ).json()["letter"]

        token_b, _ = await login(client, telegram_id=2)
        r = await client.patch(
            f"/api/letters/{created['id']}",
            headers=auth_headers(token_b),
            json={"used_in_application": True},
        )
        assert r.status_code == 404


class TestListLetters:
    async def test_list_returns_newest_first(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mock = MockLLMProvider(
            responses=[
                good_letter_response(letter_text="Первое письмо. " * 15),
                good_letter_response(letter_text="Второе письмо. " * 15),
                good_letter_response(letter_text="Третье письмо. " * 15),
            ]
        )
        _use_mock_llm(mock)

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        for _ in range(3):
            await client.post(
                f"/api/vacancies/{vacancy.id}/letter?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={},
            )

        r = await client.get(f"/api/profiles/{profile['id']}/letters", headers=auth_headers(token))
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 3
        # Сортировка newest-first по id (desc) — id-3 первый
        assert items[0]["id"] > items[1]["id"] > items[2]["id"]

    async def test_list_other_user_profile_404(self, client: AsyncClient) -> None:
        _use_mock_llm(MockLLMProvider(response=good_letter_response()))
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        token_b, _ = await login(client, telegram_id=2)
        r = await client.get(
            f"/api/profiles/{profile_a['id']}/letters", headers=auth_headers(token_b)
        )
        assert r.status_code == 404
