"""Unit-тесты HhSource: маппинг JSON → ParsedVacancy, формирование query params,
обработка 429 и сетевых ошибок.

httpx.AsyncClient мокается через MockTransport — реального сетевого слоя нет.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from src.domain.profile import Profile
from src.sources.base import SourceError, SourceRateLimitedError
from src.sources.hh import HhSource, _map_item_to_parsed, _profile_to_query_params


def _profile(**overrides: Any) -> Profile:
    base: dict[str, Any] = {
        "id": 1,
        "user_id": 1,
        "name": "Backend",
        "category": "it",
        "stack": ["python", "fastapi"],
        "grade": "middle",
        "salary_from": 200000,
        "salary_to": None,
        "salary_currency": "RUR",
        "work_format": ["remote"],
        "schedule": ["fullDay"],
        "area_ids": [1, 2],
        "exclude_keywords": [],
        "has_resume": False,
        "category_data": None,
        "is_active": True,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return Profile.model_validate(base)


# ============================================================================
# Mapping JSON -> ParsedVacancy
# ============================================================================


class TestMapItem:
    def test_minimal_item(self) -> None:
        item = {"id": "123", "name": "Backend dev"}
        parsed = _map_item_to_parsed(item)
        assert parsed.external_id == "123"
        assert parsed.source_type == "hh"
        assert parsed.title == "Backend dev"
        assert parsed.salary_from is None
        assert parsed.salary_to is None
        assert parsed.company_name is None
        assert parsed.raw_data == item

    def test_full_item(self) -> None:
        item = {
            "id": "999",
            "name": "Senior Python",
            "employer": {"id": 7, "name": "Acme"},
            "salary": {"from": 300000, "to": 500000, "currency": "RUR"},
            "alternate_url": "https://hh.ru/vacancy/999",
            "area": {"name": "Москва"},
            "schedule": {"id": "remote"},
            "experience": {"id": "moreThan6"},
            "published_at": "2026-05-21T15:30:00+0300",
        }
        parsed = _map_item_to_parsed(item)
        assert parsed.external_id == "999"
        assert parsed.title == "Senior Python"
        assert parsed.company_name == "Acme"
        assert parsed.company_id == "7"
        assert parsed.salary_from == 300000
        assert parsed.salary_to == 500000
        assert parsed.salary_currency == "RUR"
        assert parsed.url == "https://hh.ru/vacancy/999"
        assert parsed.area_name == "Москва"
        assert parsed.schedule == "remote"
        assert parsed.experience == "moreThan6"
        assert parsed.published_at is not None
        assert parsed.published_at.year == 2026
        # description и key_skills всегда пустые при short-парсинге
        assert parsed.description is None
        assert parsed.key_skills == []

    def test_employer_without_id(self) -> None:
        item = {"id": "1", "name": "X", "employer": {"name": "Acme"}}
        parsed = _map_item_to_parsed(item)
        assert parsed.company_id is None
        assert parsed.company_name == "Acme"

    def test_null_salary(self) -> None:
        item = {"id": "1", "name": "X", "salary": None}
        parsed = _map_item_to_parsed(item)
        assert parsed.salary_from is None
        assert parsed.salary_currency is None

    def test_invalid_published_at_doesnt_break(self) -> None:
        item = {"id": "1", "name": "X", "published_at": "not-a-date"}
        parsed = _map_item_to_parsed(item)
        assert parsed.published_at is None


# ============================================================================
# Profile -> hh query params
# ============================================================================


class TestProfileToQueryParams:
    def test_basic_translation(self) -> None:
        params = _profile_to_query_params(_profile(), search_params=None)
        assert params["text"] == "python fastapi"
        assert params["area"] == [1, 2]
        assert params["salary"] == 200000
        assert params["only_with_salary"] == "true"
        assert params["schedule"] == "remote"  # remote в work_format → schedule
        assert params["experience"] == "between3And6"  # middle
        assert "page" in params and params["page"] == 0
        assert params["order_by"] == "publication_time"

    def test_no_remote_no_schedule_param(self) -> None:
        p = _profile(work_format=["hybrid", "office"])
        params = _profile_to_query_params(p, None)
        assert "schedule" not in params

    def test_no_salary_omits_only_with_salary(self) -> None:
        p = _profile(salary_from=None)
        params = _profile_to_query_params(p, None)
        assert "salary" not in params
        assert "only_with_salary" not in params

    def test_empty_stack_omits_text(self) -> None:
        p = _profile(stack=[])
        params = _profile_to_query_params(p, None)
        assert "text" not in params

    def test_search_params_override(self) -> None:
        p = _profile()
        params = _profile_to_query_params(p, {"period": 30, "text": "django"})
        assert params["period"] == 30
        assert params["text"] == "django"

    def test_grade_mapping(self) -> None:
        cases = {
            "junior": "between1And3",
            "middle": "between3And6",
            "senior": "moreThan6",
            "lead": "moreThan6",
        }
        for grade, expected_exp in cases.items():
            p = _profile(grade=grade)
            params = _profile_to_query_params(p, None)
            assert params["experience"] == expected_exp


# ============================================================================
# HhSource.fetch over MockTransport
# ============================================================================


def _mock_client(handler: Any) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(
        base_url="https://api.hh.ru",
        transport=transport,
        headers={"User-Agent": "test"},
    )


class TestFetch:
    async def test_fetch_single_page(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/vacancies"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "1", "name": "First"},
                        {"id": "2", "name": "Second"},
                    ],
                    "pages": 1,
                },
            )

        source = HhSource(client=_mock_client(handler))
        result = await source.fetch(_profile())
        assert len(result) == 2
        assert result[0].external_id == "1"
        assert result[1].title == "Second"

    async def test_fetch_paginates(self) -> None:
        seen_pages = []

        def handler(request: httpx.Request) -> httpx.Response:
            page = int(request.url.params.get("page", "0"))
            seen_pages.append(page)
            return httpx.Response(
                200,
                json={
                    "items": [{"id": f"p{page}_1", "name": "X"}],
                    "pages": 3,
                },
            )

        source = HhSource(client=_mock_client(handler))
        result = await source.fetch(_profile())
        # Должны пройти 3 страницы (или max_pages, что меньше)
        assert len(result) == 3
        assert seen_pages == [0, 1, 2]

    async def test_fetch_429_raises_rate_limited(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="too many requests")

        source = HhSource(client=_mock_client(handler))
        with pytest.raises(SourceRateLimitedError):
            await source.fetch(_profile())

    async def test_fetch_500_raises_source_error(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="server error")

        source = HhSource(client=_mock_client(handler))
        with pytest.raises(SourceError, match="500"):
            await source.fetch(_profile())

    async def test_fetch_non_json_raises_source_error(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>nope</html>")

        source = HhSource(client=_mock_client(handler))
        with pytest.raises(SourceError, match="non-JSON"):
            await source.fetch(_profile())

    async def test_fetch_skips_malformed_items(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "1", "name": "Good"},
                        # Этот item не должен сломать парсинг остального
                        {"id": None, "name": "Bad"},
                    ],
                    "pages": 1,
                },
            )

        source = HhSource(client=_mock_client(handler))
        # Не падает — bad item получит external_id="None" (str(None))
        result = await source.fetch(_profile())
        assert len(result) == 2


class TestFetchDetails:
    async def test_fetch_details_returns_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/vacancies/12345"
            return httpx.Response(200, json={"id": "12345", "description": "<p>job</p>"})

        source = HhSource(client=_mock_client(handler))
        details = await source.fetch_details("12345")
        assert details is not None
        assert details["description"] == "<p>job</p>"

    async def test_fetch_details_404_returns_none(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        source = HhSource(client=_mock_client(handler))
        assert await source.fetch_details("missing") is None

    async def test_fetch_details_429_raises(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(429)

        source = HhSource(client=_mock_client(handler))
        with pytest.raises(SourceRateLimitedError):
            await source.fetch_details("x")
