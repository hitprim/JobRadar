"""Парсер hh.ru через публичный анонимный API.

ВАЖНО: соискательский OAuth у hh.ru ОТКЛЮЧЁН с 15.12.2025.
Используем только публичный endpoint `GET /vacancies` (поиск) и
`GET /vacancies/{id}` (детали) без авторизации.

Поведение:
- Параметры запроса формируются из полей Profile + опционально search_params.
- При парсинге берём только short-info из списка (title, salary, employer,
  url, area, schedule, experience, published_at). description / key_skills
  загружаются позже on-demand через `fetch_details`.
- При 429 кидаем SourceRateLimitedError. На сетевые ошибки — SourceError.

Документация API:
- https://github.com/hhru/api/blob/master/docs/vacancies.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from src.config import settings
from src.domain.profile import Profile
from src.domain.vacancy import ParsedVacancy
from src.sources.base import Source, SourceError, SourceRateLimitedError


def _build_user_agent() -> str:
    """hh.ru требует User-Agent с контактом."""
    return f"JobRadar/0.1 ({settings.hh_user_agent_contact})"


def _profile_to_query_params(
    profile: Profile, search_params: dict[str, Any] | None
) -> dict[str, Any]:
    """Маппинг наших generic-полей в специфичные параметры hh.ru.

    https://github.com/hhru/api/blob/master/docs/general.md#vacancy-search
    """
    params: dict[str, Any] = {
        # Текст поиска: пока — конкатенация стека (например "python fastapi")
        "text": " ".join(profile.stack) if profile.stack else "",
        "per_page": settings.parser_per_page,
        "page": 0,
        # Свежие вакансии
        "period": settings.parser_period_days,
        "order_by": "publication_time",
    }

    if profile.area_ids:
        # hh.ru принимает несколько area параметров — в httpx это list
        params["area"] = profile.area_ids

    if profile.salary_from:
        params["salary"] = profile.salary_from
        params["only_with_salary"] = "true"

    # work_format → schedule (hh не различает remote от work_format)
    # remote → "remote", hybrid/office не имеют прямого 1:1
    if profile.work_format and "remote" in profile.work_format:
        params["schedule"] = "remote"

    # grade → experience (грубый mapping)
    if profile.grade:
        grade_map = {
            "junior": "between1And3",
            "middle": "between3And6",
            "senior": "moreThan6",
            "lead": "moreThan6",
        }
        if profile.grade in grade_map:
            params["experience"] = grade_map[profile.grade]

    # Доп. фильтры из search_params (period override, custom text и т.п.)
    if search_params:
        for key in ("period", "order_by", "text", "experience", "schedule"):
            if key in search_params:
                params[key] = search_params[key]

    return {k: v for k, v in params.items() if v not in (None, "", [])}


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    # hh.ru возвращает '2024-05-21T15:30:00+0300' (без двоеточия в TZ)
    try:
        # Python 3.11+ парсит большинство ISO 8601 вариантов
        return datetime.fromisoformat(value)
    except ValueError:
        # На случай старого формата
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None


def _map_item_to_parsed(item: dict[str, Any]) -> ParsedVacancy:
    """Маппинг одного элемента search-response в ParsedVacancy."""
    salary = item.get("salary") or {}
    employer = item.get("employer") or {}
    area = item.get("area") or {}
    schedule = item.get("schedule") or {}
    experience = item.get("experience") or {}

    return ParsedVacancy(
        external_id=str(item.get("id", "")),
        source_type="hh",
        title=item.get("name"),
        company_name=employer.get("name"),
        company_id=str(employer["id"]) if employer.get("id") is not None else None,
        salary_from=salary.get("from"),
        salary_to=salary.get("to"),
        salary_currency=salary.get("currency"),
        url=item.get("alternate_url"),
        area_name=area.get("name"),
        schedule=schedule.get("id"),
        experience=experience.get("id"),
        description=None,  # в short-info нет; подгрузим on-demand
        key_skills=[],  # тоже только в full vacancy
        published_at=_parse_iso_datetime(item.get("published_at")),
        raw_data=item,
    )


class HhSource(Source):
    source_type = "hh"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client  # для тестов можно передать настроенный mock

    def _build_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            base_url=settings.hh_api_base_url,
            headers={"User-Agent": _build_user_agent()},
            timeout=settings.parser_http_timeout_seconds,
        )

    async def fetch(
        self, profile: Profile, search_params: dict[str, Any] | None = None
    ) -> list[ParsedVacancy]:
        query = _profile_to_query_params(profile, search_params)
        max_pages = settings.parser_max_pages
        results: list[ParsedVacancy] = []

        client = self._build_client()
        owns_client = self._client is None
        try:
            for page in range(max_pages):
                query["page"] = page
                try:
                    response = await client.get("/vacancies", params=query)
                except httpx.HTTPError as exc:
                    raise SourceError(f"hh.ru request failed: {exc}") from exc

                if response.status_code == 429:
                    raise SourceRateLimitedError("hh.ru returned 429")
                if response.status_code >= 400:
                    raise SourceError(
                        f"hh.ru returned {response.status_code}: {response.text[:200]}"
                    )

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise SourceError(f"hh.ru returned non-JSON: {exc}") from exc

                items = payload.get("items") or []
                for item in items:
                    try:
                        results.append(_map_item_to_parsed(item))
                    except Exception as exc:
                        logger.bind(item_id=item.get("id")).warning(
                            "hh parser: failed to map item: {}", exc
                        )

                # Стоп если pages исчерпаны
                pages_count = payload.get("pages", 0)
                if page + 1 >= pages_count:
                    break
        finally:
            if owns_client:
                await client.aclose()

        return results

    async def fetch_details(self, external_id: str) -> dict[str, Any] | None:
        """Подгружает full info о вакансии (description, key_skills, ...)."""
        client = self._build_client()
        owns_client = self._client is None
        try:
            try:
                response = await client.get(f"/vacancies/{external_id}")
            except httpx.HTTPError as exc:
                raise SourceError(f"hh.ru details request failed: {exc}") from exc

            if response.status_code == 404:
                return None
            if response.status_code == 429:
                raise SourceRateLimitedError("hh.ru returned 429 on details")
            if response.status_code >= 400:
                raise SourceError(
                    f"hh.ru details returned {response.status_code}: {response.text[:200]}"
                )
            return response.json()
        finally:
            if owns_client:
                await client.aclose()
