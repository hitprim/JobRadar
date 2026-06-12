"""Integration-тесты feed и vacancies/reaction endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import SourceVacancy as SourceVacancyORM
from src.db.models import Vacancy as VacancyORM
from tests.integration.auth_helpers import auth_headers, login

pytestmark = pytest.mark.asyncio


async def _setup_profile_with_source(client: AsyncClient, token: str) -> tuple[dict, dict]:
    profile = (
        await client.post(
            "/api/profiles",
            headers=auth_headers(token),
            json={"name": "Backend", "category": "it", "grade": "middle", "stack": ["python"]},
        )
    ).json()
    source = (
        await client.post(
            f"/api/profiles/{profile['id']}/sources",
            headers=auth_headers(token),
            json={"type": "hh"},
        )
    ).json()
    return profile, source


async def _seed_vacancy(
    session: AsyncSession,
    *,
    external_id: str = "v1",
    title: str = "Vacancy 1",
    published_at: datetime | None = None,
    link_source_id: int | None = None,
) -> VacancyORM:
    v = VacancyORM(
        external_id=external_id,
        source_type="hh",
        title=title,
        company_name="Acme",
        salary_from=200000,
        url=f"https://hh.ru/vacancy/{external_id}",
        published_at=published_at or datetime.now(UTC),
    )
    session.add(v)
    await session.commit()
    await session.refresh(v)
    # Лента показывает только вакансии из актуального результата парсинга
    # источника (таблица source_vacancies). Без связи вакансия в feed не попадёт.
    if link_source_id is not None:
        session.add(SourceVacancyORM(source_id=link_source_id, vacancy_id=v.id))
        await session.commit()
    return v


class TestFeed:
    async def test_empty_feed_for_new_profile(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile, _ = await _setup_profile_with_source(client, token)
        r = await client.get(f"/api/profiles/{profile['id']}/feed", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json() == []

    async def test_feed_returns_vacancies_sorted_by_published_desc(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile, source = await _setup_profile_with_source(client, token)

        # Подсадим 3 вакансии с разными published_at
        now = datetime.now(UTC)
        await _seed_vacancy(
            db_session,
            external_id="old",
            title="Old",
            published_at=now - timedelta(days=3),
            link_source_id=source["id"],
        )
        await _seed_vacancy(
            db_session,
            external_id="mid",
            title="Mid",
            published_at=now - timedelta(days=1),
            link_source_id=source["id"],
        )
        await _seed_vacancy(
            db_session,
            external_id="new",
            title="New",
            published_at=now,
            link_source_id=source["id"],
        )

        r = await client.get(f"/api/profiles/{profile['id']}/feed", headers=auth_headers(token))
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 3
        titles = [i["vacancy"]["title"] for i in items]
        assert titles == ["New", "Mid", "Old"]
        # У новой профиля реакций ещё нет
        assert all(i["reaction"] is None for i in items)

    async def test_feed_pagination(self, client: AsyncClient, db_session: AsyncSession) -> None:
        token, _ = await login(client)
        profile, source = await _setup_profile_with_source(client, token)

        for i in range(5):
            await _seed_vacancy(
                db_session,
                external_id=f"v{i}",
                title=f"V{i}",
                published_at=datetime.now(UTC) - timedelta(hours=i),
                link_source_id=source["id"],
            )

        r1 = await client.get(
            f"/api/profiles/{profile['id']}/feed?limit=2&offset=0",
            headers=auth_headers(token),
        )
        r2 = await client.get(
            f"/api/profiles/{profile['id']}/feed?limit=2&offset=2",
            headers=auth_headers(token),
        )
        assert len(r1.json()) == 2
        assert len(r2.json()) == 2
        assert r1.json()[0]["vacancy"]["id"] != r2.json()[0]["vacancy"]["id"]

    async def test_feed_without_active_source_returns_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        # Создаём профиль БЕЗ источника — feed пустой даже если есть вакансии
        token, _ = await login(client)
        profile = (
            await client.post(
                "/api/profiles",
                headers=auth_headers(token),
                json={"name": "P", "category": "it"},
            )
        ).json()
        await _seed_vacancy(db_session)
        r = await client.get(f"/api/profiles/{profile['id']}/feed", headers=auth_headers(token))
        assert r.json() == []

    async def test_other_user_cannot_see_feed(self, client: AsyncClient) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a, _ = await _setup_profile_with_source(client, token_a)
        token_b, _ = await login(client, telegram_id=2)
        r = await client.get(f"/api/profiles/{profile_a['id']}/feed", headers=auth_headers(token_b))
        assert r.status_code == 404


class TestFeedReactionFilter:
    async def _seed_three_with_reactions(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> tuple[str, dict, dict[str, VacancyORM]]:
        """Лайкнутая / сохранённая / пропущенная вакансии в ленте профиля."""
        token, _ = await login(client)
        profile, source = await _setup_profile_with_source(client, token)
        vacs = {}
        for ext, react in (("liked", "like"), ("saved", "save"), ("skipped", "skip")):
            v = await _seed_vacancy(
                db_session, external_id=ext, title=ext, link_source_id=source["id"]
            )
            vacs[react] = v
            r = await client.post(
                f"/api/vacancies/{v.id}/reaction?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"reaction": react},
            )
            assert r.status_code == 200, r.text
        return token, profile, vacs

    async def test_default_feed_hides_skipped(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, profile, _ = await self._seed_three_with_reactions(client, db_session)
        r = await client.get(f"/api/profiles/{profile['id']}/feed", headers=auth_headers(token))
        titles = {i["vacancy"]["title"] for i in r.json()}
        assert titles == {"liked", "saved"}  # skipped спрятана

    async def test_filter_like_returns_only_liked(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, profile, _ = await self._seed_three_with_reactions(client, db_session)
        r = await client.get(
            f"/api/profiles/{profile['id']}/feed?reaction=like", headers=auth_headers(token)
        )
        titles = [i["vacancy"]["title"] for i in r.json()]
        assert titles == ["liked"]

    async def test_filter_save_returns_only_saved(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, profile, _ = await self._seed_three_with_reactions(client, db_session)
        r = await client.get(
            f"/api/profiles/{profile['id']}/feed?reaction=save", headers=auth_headers(token)
        )
        titles = [i["vacancy"]["title"] for i in r.json()]
        assert titles == ["saved"]

    async def test_filter_all_includes_skipped(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, profile, _ = await self._seed_three_with_reactions(client, db_session)
        r = await client.get(
            f"/api/profiles/{profile['id']}/feed?reaction=all", headers=auth_headers(token)
        )
        titles = {i["vacancy"]["title"] for i in r.json()}
        assert titles == {"liked", "saved", "skipped"}

    async def test_invalid_reaction_filter_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, profile, _ = await self._seed_three_with_reactions(client, db_session)
        r = await client.get(
            f"/api/profiles/{profile['id']}/feed?reaction=bogus", headers=auth_headers(token)
        )
        assert r.status_code == 422


class TestVacancyDetails:
    async def test_get_vacancy_404(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        r = await client.get("/api/vacancies/99999", headers=auth_headers(token))
        assert r.status_code == 404

    async def test_get_vacancy_with_description_returned_as_is(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        token, _ = await login(client)
        # Подсадим вакансию с уже заполненным description — fetch_details не должна дёргаться
        v = await _seed_vacancy(db_session)
        v.description = "Pre-filled"
        await db_session.commit()

        called = []

        async def _fake_fetch_details(self, ext_id):  # type: ignore[no-untyped-def]
            called.append(ext_id)
            return None

        from src.sources.hh_chrome import HhChromeSource

        monkeypatch.setattr(HhChromeSource, "fetch_details", _fake_fetch_details)

        r = await client.get(f"/api/vacancies/{v.id}", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()["description"] == "Pre-filled"
        assert called == []  # lazy fetch не вызывалась

    async def test_get_vacancy_triggers_lazy_fetch_details(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        token, _ = await login(client)
        v = await _seed_vacancy(db_session)  # description=None

        async def _fake_fetch_details(self, ext_id):  # type: ignore[no-untyped-def]
            return {
                "description": "Full description",
                "key_skills": [{"name": "python"}, {"name": "fastapi"}],
            }

        from src.sources.hh_chrome import HhChromeSource

        monkeypatch.setattr(HhChromeSource, "fetch_details", _fake_fetch_details)

        # Первый запрос: description ещё None, GET возвращается сразу с
        # description_pending=true, а подгрузка идёт в фоне (background task).
        r = await client.get(f"/api/vacancies/{v.id}", headers=auth_headers(token))
        assert r.status_code == 200
        body = r.json()
        assert body["description"] is None
        assert body["description_pending"] is True

        # Под ASGITransport background task успевает доработать до возврата ответа,
        # поэтому при повторном опросе description уже в БД.
        r2 = await client.get(f"/api/vacancies/{v.id}", headers=auth_headers(token))
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["description"] == "Full description"
        assert body2["key_skills"] == ["python", "fastapi"]
        assert body2["description_pending"] is False

        # Третий запрос — description уже в БД, fetch_details не должна вызываться
        called = []

        async def _fail_fetch(self, ext_id):  # type: ignore[no-untyped-def]
            called.append(ext_id)
            return None

        monkeypatch.setattr(HhChromeSource, "fetch_details", _fail_fetch)
        r3 = await client.get(f"/api/vacancies/{v.id}", headers=auth_headers(token))
        assert r3.status_code == 200
        assert called == []

    async def test_get_vacancy_network_failure_returns_what_we_have(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from src.sources.base import SourceError
        from src.sources.hh_chrome import HhChromeSource

        async def _boom(self, ext_id):  # type: ignore[no-untyped-def]
            raise SourceError("network down")

        monkeypatch.setattr(HhChromeSource, "fetch_details", _boom)

        token, _ = await login(client)
        v = await _seed_vacancy(db_session)
        r = await client.get(f"/api/vacancies/{v.id}", headers=auth_headers(token))
        assert r.status_code == 200
        body = r.json()
        # GET возвращается сразу; фон упал с SourceError — description остался None.
        assert body["description"] is None
        assert body["description_pending"] is True

        # SourceError не помечает details_fetched → повторный опрос снова пробует.
        # На этот раз fetch отдаёт описание, и оно дописывается в фоне.
        from src.sources.hh_chrome import HhChromeSource

        async def _ok(self, ext_id):  # type: ignore[no-untyped-def]
            return {"description": "Recovered", "key_skills": []}

        monkeypatch.setattr(HhChromeSource, "fetch_details", _ok)
        await client.get(f"/api/vacancies/{v.id}", headers=auth_headers(token))
        r2 = await client.get(f"/api/vacancies/{v.id}", headers=auth_headers(token))
        assert r2.json()["description"] == "Recovered"


class TestReactions:
    async def test_react_like(self, client: AsyncClient, db_session: AsyncSession) -> None:
        token, _ = await login(client)
        profile, source = await _setup_profile_with_source(client, token)
        v = await _seed_vacancy(db_session, link_source_id=source["id"])

        r = await client.post(
            f"/api/vacancies/{v.id}/reaction?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={"reaction": "like"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["reaction"] == "like"

        # В feed реакция теперь видна
        feed = await client.get(f"/api/profiles/{profile['id']}/feed", headers=auth_headers(token))
        item = feed.json()[0]
        assert item["reaction"]["reaction"] == "like"

    async def test_react_upsert_changes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile, _ = await _setup_profile_with_source(client, token)
        v = await _seed_vacancy(db_session)

        for action in ("like", "skip", "save"):
            r = await client.post(
                f"/api/vacancies/{v.id}/reaction?profile_id={profile['id']}",
                headers=auth_headers(token),
                json={"reaction": action},
            )
            assert r.status_code == 200
            assert r.json()["reaction"] == action

    async def test_invalid_reaction_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token, _ = await login(client)
        profile, _ = await _setup_profile_with_source(client, token)
        v = await _seed_vacancy(db_session)
        r = await client.post(
            f"/api/vacancies/{v.id}/reaction?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={"reaction": "yeet"},
        )
        assert r.status_code == 422

    async def test_react_other_users_profile_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token_a, _ = await login(client, telegram_id=1)
        profile_a, _ = await _setup_profile_with_source(client, token_a)
        v = await _seed_vacancy(db_session)

        token_b, _ = await login(client, telegram_id=2)
        r = await client.post(
            f"/api/vacancies/{v.id}/reaction?profile_id={profile_a['id']}",
            headers=auth_headers(token_b),
            json={"reaction": "like"},
        )
        assert r.status_code == 404

    async def test_react_unknown_vacancy(self, client: AsyncClient) -> None:
        token, _ = await login(client)
        profile, _ = await _setup_profile_with_source(client, token)
        r = await client.post(
            f"/api/vacancies/99999/reaction?profile_id={profile['id']}",
            headers=auth_headers(token),
            json={"reaction": "like"},
        )
        assert r.status_code == 404
