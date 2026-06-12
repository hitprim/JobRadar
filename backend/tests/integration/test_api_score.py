"""Integration-тесты POST /api/vacancies/{id}/score."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import SourceVacancy as SourceVacancyORM
from src.db.models import Vacancy as VacancyORM
from src.llm import get_llm_provider
from src.main import app
from tests.integration.auth_helpers import auth_headers, login
from tests.integration.mocks import MockLLMProvider, good_scoring_response

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
                "stack": ["python"],
                "salary_from": 200000,
            },
        )
    ).json()


async def _seed_vacancy(session: AsyncSession, **kwargs) -> VacancyORM:
    defaults: dict = {
        "external_id": "vac-1",
        "source_type": "hh",
        "title": "Senior Python",
        "company_name": "Acme",
        "salary_from": 300000,
        "salary_currency": "RUR",
        "url": "https://hh.ru/vacancy/vac-1",
        "area_name": "Москва",
        "schedule": "remote",
        "experience": "moreThan6",
        "description": "Backend dev на Python и FastAPI",
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


class TestScoreEndpoint:
    async def test_scores_vacancy_and_caches(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mock = MockLLMProvider(
            response=good_scoring_response(score=85, reason="Стек совпадает, грейд senior, зп ок.")
        )
        _use_mock_llm(mock)

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        r = await client.post(
            f"/api/vacancies/{vacancy.id}/score?profile_id={profile['id']}",
            headers=auth_headers(token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["score"] == 85
        assert "Стек" in body["reason"]
        assert body["from_cache"] is False
        assert mock.call_count == 1

        # Повторный вызов — должен взять из кэша, LLM не дёргается
        r2 = await client.post(
            f"/api/vacancies/{vacancy.id}/score?profile_id={profile['id']}",
            headers=auth_headers(token),
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["score"] == 85
        assert body2["from_cache"] is True
        assert mock.call_count == 1  # не увеличилось

    async def test_force_rescore_calls_llm_again(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mock = MockLLMProvider(
            responses=[
                good_scoring_response(score=50, reason="Первая оценка - не очень."),
                good_scoring_response(score=90, reason="Передумали, отличный матч."),
            ]
        )
        _use_mock_llm(mock)

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        # Первый scoring
        r1 = await client.post(
            f"/api/vacancies/{vacancy.id}/score?profile_id={profile['id']}",
            headers=auth_headers(token),
        )
        assert r1.json()["score"] == 50
        assert mock.call_count == 1

        # force=True → должен дёрнуть LLM снова
        r2 = await client.post(
            f"/api/vacancies/{vacancy.id}/score?profile_id={profile['id']}&force=true",
            headers=auth_headers(token),
        )
        assert r2.status_code == 200
        assert r2.json()["score"] == 90
        assert r2.json()["from_cache"] is False
        assert mock.call_count == 2

    async def test_score_propagates_to_feed(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        mock = MockLLMProvider(response=good_scoring_response(score=70, reason="OK matchings"))
        _use_mock_llm(mock)

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        # источник нужен чтобы вакансия попала в feed
        source = (
            await client.post(
                f"/api/profiles/{profile['id']}/sources",
                headers=auth_headers(token),
                json={"type": "hh"},
            )
        ).json()
        vacancy = await _seed_vacancy(db_session)
        # Лента берёт вакансии из source_vacancies — связываем вручную
        db_session.add(SourceVacancyORM(source_id=source["id"], vacancy_id=vacancy.id))
        await db_session.commit()

        # Скорим
        await client.post(
            f"/api/vacancies/{vacancy.id}/score?profile_id={profile['id']}",
            headers=auth_headers(token),
        )

        # В feed теперь есть reaction со score
        feed = await client.get(f"/api/profiles/{profile['id']}/feed", headers=auth_headers(token))
        items = feed.json()
        assert len(items) == 1
        assert items[0]["reaction"]["score"] == 70

    async def test_unknown_vacancy_returns_404(self, client: AsyncClient) -> None:
        _use_mock_llm(MockLLMProvider(response=good_scoring_response()))
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        r = await client.post(
            f"/api/vacancies/99999/score?profile_id={profile['id']}",
            headers=auth_headers(token),
        )
        assert r.status_code == 404

    async def test_other_users_profile_returns_404(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _use_mock_llm(MockLLMProvider(response=good_scoring_response()))

        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        vacancy = await _seed_vacancy(db_session)

        token_b, _ = await login(client, telegram_id=2)
        r = await client.post(
            f"/api/vacancies/{vacancy.id}/score?profile_id={profile_a['id']}",
            headers=auth_headers(token_b),
        )
        assert r.status_code == 404

    async def test_llm_error_returns_502(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from src.llm.base import LLMProvider

        class _FailingLLM(LLMProvider):
            async def complete(self, *, system, user, response_schema):  # type: ignore[override]
                from src.llm.base import LLMUnavailableError

                raise LLMUnavailableError("simulated outage")

        app.dependency_overrides[get_llm_provider] = lambda: _FailingLLM()

        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        r = await client.post(
            f"/api/vacancies/{vacancy.id}/score?profile_id={profile['id']}",
            headers=auth_headers(token),
        )
        assert r.status_code == 502
        assert "outage" in r.json()["detail"]

    async def test_score_includes_resume_when_present(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Если у профиля есть резюме, оно попадает в user-message промпта."""
        mock = MockLLMProvider(
            response=good_scoring_response(score=88, reason="Резюме сильно подходит.")
        )
        _use_mock_llm(mock)

        token, _ = await login(client)
        profile = await _setup_profile(client, token)

        # Загружаем резюме
        unique_text = "Senior Python with 7 years of FastAPI experience. UNIQUE-MARKER-42."
        await client.put(
            f"/api/profiles/{profile['id']}/resume",
            headers=auth_headers(token),
            json={"resume_text": unique_text},
        )

        vacancy = await _seed_vacancy(db_session)

        r = await client.post(
            f"/api/vacancies/{vacancy.id}/score?profile_id={profile['id']}",
            headers=auth_headers(token),
        )
        assert r.status_code == 200
        # Резюме должно быть в user-message LLM-вызова (дешифрованное)
        assert mock.call_count == 1
        assert "UNIQUE-MARKER-42" in mock.last_user_message()
