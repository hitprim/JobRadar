"""Integration-тесты отзывов о компаниях (об отношении к соискателям)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import SourceVacancy as SourceVacancyORM
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


async def _setup_source(client: AsyncClient, token: str, profile_id: int) -> dict:
    return (
        await client.post(
            f"/api/profiles/{profile_id}/sources",
            headers=auth_headers(token),
            json={"type": "hh"},
        )
    ).json()


async def _seed_vacancy(
    session: AsyncSession,
    *,
    external_id: str = "cr-1",
    company_id: str | None = "emp-1",
    company_name: str | None = "Acme",
    link_source_id: int | None = None,
) -> VacancyORM:
    v = VacancyORM(
        external_id=external_id,
        source_type="hh",
        title="Backend Dev",
        company_id=company_id,
        company_name=company_name,
        url=f"https://hh.ru/vacancy/{external_id}",
        published_at=datetime.now(UTC),
    )
    session.add(v)
    await session.commit()
    await session.refresh(v)
    if link_source_id is not None:
        session.add(SourceVacancyORM(source_id=link_source_id, vacancy_id=v.id))
        await session.commit()
    return v


async def _apply(client: AsyncClient, token: str, profile_id: int, vacancy_id: int) -> None:
    r = await client.post(
        f"/api/applications?profile_id={profile_id}",
        headers=auth_headers(token),
        json={"vacancy_id": vacancy_id},
    )
    assert r.status_code == 201, r.text


_GOOD_REVIEW = {
    "responded": "fast",
    "respect": "respectful",
    "feedback": "detailed",
    "honesty": "matched",
    "process": "smooth",
    "text": "Отвечали быстро, общались по-человечески.",
}


# ============================================================================
# GET (view)
# ============================================================================


class TestGetView:
    async def test_view_no_reviews(self, client: AsyncClient, db_session: AsyncSession) -> None:
        token, _ = await login(client)
        await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        r = await client.get(
            f"/api/vacancies/{vacancy.id}/company-review", headers=auth_headers(token)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["company_key"] == "id:emp-1"
        assert body["review_count"] == 0
        assert body["respect_score"] is None
        assert body["can_review"] is False  # нет отклика
        assert body["my_review"] is None
        assert body["reviews"] == []

    async def test_view_can_review_after_application(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        await _apply(client, token, profile["id"], vacancy.id)

        r = await client.get(
            f"/api/vacancies/{vacancy.id}/company-review", headers=auth_headers(token)
        )
        assert r.json()["can_review"] is True

    async def test_view_unknown_vacancy_404(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        await _setup_profile(client, token)
        r = await client.get("/api/vacancies/999999/company-review", headers=auth_headers(token))
        assert r.status_code == 404


# ============================================================================
# POST (submit)
# ============================================================================


class TestSubmit:
    async def test_submit_without_application_forbidden(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)

        r = await client.post(
            f"/api/vacancies/{vacancy.id}/company-review",
            headers=auth_headers(token),
            json=_GOOD_REVIEW,
        )
        assert r.status_code == 403

    async def test_submit_after_application_succeeds(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        await _apply(client, token, profile["id"], vacancy.id)

        r = await client.post(
            f"/api/vacancies/{vacancy.id}/company-review?profile_id={profile['id']}",
            headers=auth_headers(token),
            json=_GOOD_REVIEW,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["review_count"] == 1
        assert body["respect_score"] == 100  # все сигналы — лучшие
        assert body["my_review"] is not None
        assert body["my_review"]["text"] == _GOOD_REVIEW["text"]
        assert len(body["reviews"]) == 1

    async def test_resubmit_updates_not_duplicates(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        await _apply(client, token, profile["id"], vacancy.id)

        await client.post(
            f"/api/vacancies/{vacancy.id}/company-review",
            headers=auth_headers(token),
            json=_GOOD_REVIEW,
        )
        # Повторно — но уже худшие сигналы.
        r = await client.post(
            f"/api/vacancies/{vacancy.id}/company-review",
            headers=auth_headers(token),
            json={
                "responded": "ignored",
                "respect": "dismissive",
                "feedback": "none",
                "honesty": "mismatch",
                "process": "draining",
                "text": None,
            },
        )
        body = r.json()
        assert body["review_count"] == 1  # не дублируется
        assert body["respect_score"] == 0

    async def test_verification_works_across_company_vacancies(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Отклик на вакансию A компании даёт право на отзыв через вакансию B той же компании."""
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vac_a = await _seed_vacancy(db_session, external_id="A", company_id="emp-shared")
        vac_b = await _seed_vacancy(db_session, external_id="B", company_id="emp-shared")
        await _apply(client, token, profile["id"], vac_a.id)

        r = await client.post(
            f"/api/vacancies/{vac_b.id}/company-review",
            headers=auth_headers(token),
            json=_GOOD_REVIEW,
        )
        assert r.status_code == 200, r.text

    async def test_submit_no_company_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(
            db_session, external_id="nocomp", company_id=None, company_name=None
        )
        # Даже без верификации сначала ловим «нет компании» → 422.
        await _apply(client, token, profile["id"], vacancy.id)
        r = await client.post(
            f"/api/vacancies/{vacancy.id}/company-review",
            headers=auth_headers(token),
            json=_GOOD_REVIEW,
        )
        assert r.status_code == 422

    async def test_invalid_signal_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        vacancy = await _seed_vacancy(db_session)
        await _apply(client, token, profile["id"], vacancy.id)
        r = await client.post(
            f"/api/vacancies/{vacancy.id}/company-review",
            headers=auth_headers(token),
            json={**_GOOD_REVIEW, "respect": "godlike"},
        )
        assert r.status_code == 422

    async def test_review_visible_to_other_user(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # User A с откликом оставляет отзыв.
        token_a, _ = await login(client, telegram_id=1)
        profile_a = await _setup_profile(client, token_a)
        vacancy = await _seed_vacancy(db_session)
        await _apply(client, token_a, profile_a["id"], vacancy.id)
        await client.post(
            f"/api/vacancies/{vacancy.id}/company-review",
            headers=auth_headers(token_a),
            json=_GOOD_REVIEW,
        )

        # User B (без отклика) видит агрегат и текст, но can_review=False.
        token_b, _ = await login(client, telegram_id=2)
        await _setup_profile(client, token_b)
        r = await client.get(
            f"/api/vacancies/{vacancy.id}/company-review", headers=auth_headers(token_b)
        )
        body = r.json()
        assert body["review_count"] == 1
        assert body["respect_score"] == 100
        assert body["can_review"] is False
        assert body["my_review"] is None
        assert len(body["reviews"]) == 1
        # Анонимность: user_id в публичном отзыве не отдаём.
        assert "user_id" not in body["reviews"][0]


# ============================================================================
# Feed badge
# ============================================================================


class TestFeedBadge:
    async def test_feed_item_carries_company_review_summary(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        source = await _setup_source(client, token, profile["id"])
        vacancy = await _seed_vacancy(db_session, link_source_id=source["id"])
        await _apply(client, token, profile["id"], vacancy.id)
        await client.post(
            f"/api/vacancies/{vacancy.id}/company-review",
            headers=auth_headers(token),
            json=_GOOD_REVIEW,
        )

        r = await client.get(f"/api/profiles/{profile['id']}/feed", headers=auth_headers(token))
        assert r.status_code == 200, r.text
        items = r.json()
        assert len(items) == 1
        assert items[0]["company_review"] is not None
        assert items[0]["company_review"]["respect_score"] == 100
        assert items[0]["company_review"]["review_count"] == 1

    async def test_feed_item_no_summary_without_reviews(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile = await _setup_profile(client, token)
        source = await _setup_source(client, token, profile["id"])
        await _seed_vacancy(db_session, link_source_id=source["id"])

        r = await client.get(f"/api/profiles/{profile['id']}/feed", headers=auth_headers(token))
        items = r.json()
        assert len(items) == 1
        assert items[0]["company_review"] is None


# ============================================================================
# Report (post-hoc модерация: авто-скрытие по жалобам)
# ============================================================================


async def _author_review(
    client: AsyncClient, db_session: AsyncSession, *, telegram_id: int = 1
) -> tuple[str, dict, int]:
    """Создаёт отзыв автором (с откликом). Возвращает (token, vacancy_dict, review_id)."""
    token, _ = await login(client, telegram_id=telegram_id)
    profile = await _setup_profile(client, token)
    vacancy = await _seed_vacancy(db_session)
    await _apply(client, token, profile["id"], vacancy.id)
    r = await client.post(
        f"/api/vacancies/{vacancy.id}/company-review",
        headers=auth_headers(token),
        json=_GOOD_REVIEW,
    )
    review_id = r.json()["my_review"]["id"]
    return token, {"id": vacancy.id}, review_id


class TestReport:
    async def test_report_increments_count(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, review_id = await _author_review(client, db_session)
        token_b, _ = await login(client, telegram_id=2)
        r = await client.post(
            f"/api/company-reviews/{review_id}/report", headers=auth_headers(token_b)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["report_count"] == 1
        assert body["hidden"] is False

    async def test_report_idempotent_per_user(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, review_id = await _author_review(client, db_session)
        token_b, _ = await login(client, telegram_id=2)
        await client.post(f"/api/company-reviews/{review_id}/report", headers=auth_headers(token_b))
        r = await client.post(
            f"/api/company-reviews/{review_id}/report", headers=auth_headers(token_b)
        )
        # Повторная жалоба того же юзера не накручивает счётчик.
        assert r.json()["report_count"] == 1
        assert r.json()["hidden"] is False

    async def test_report_hides_after_threshold(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        author_token, vacancy, review_id = await _author_review(client, db_session)
        # Три разных юзера жалуются → отзыв скрывается.
        last_hidden = False
        for tg in (2, 3, 4):
            token, _ = await login(client, telegram_id=tg)
            r = await client.post(
                f"/api/company-reviews/{review_id}/report", headers=auth_headers(token)
            )
            last_hidden = r.json()["hidden"]
        assert last_hidden is True

        # Сторонний юзер больше не видит отзыв в публичном списке/агрегате.
        token_x, _ = await login(client, telegram_id=9)
        await _setup_profile(client, token_x)
        rv = await client.get(
            f"/api/vacancies/{vacancy['id']}/company-review", headers=auth_headers(token_x)
        )
        body = rv.json()
        assert body["review_count"] == 0
        assert body["respect_score"] is None
        assert body["reviews"] == []

        # Автор по-прежнему видит свой (скрытый) отзыв.
        ra = await client.get(
            f"/api/vacancies/{vacancy['id']}/company-review", headers=auth_headers(author_token)
        )
        assert ra.json()["my_review"] is not None

    async def test_report_unknown_review_404(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        r = await client.post("/api/company-reviews/999999/report", headers=auth_headers(token))
        assert r.status_code == 404

    async def test_report_without_auth_401(self, client: AsyncClient) -> None:
        r = await client.post("/api/company-reviews/1/report")
        assert r.status_code == 401


# ============================================================================
# Auth
# ============================================================================


class TestAuthRequired:
    async def test_get_without_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/vacancies/1/company-review")
        assert r.status_code == 401

    async def test_submit_without_auth(self, client: AsyncClient) -> None:
        r = await client.post("/api/vacancies/1/company-review", json=_GOOD_REVIEW)
        assert r.status_code == 401
