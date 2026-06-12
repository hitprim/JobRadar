"""Unit-тесты headless-Chrome парсера hh.ru.

Сеть и Chrome НЕ дёргаются: parse_vacancies проверяется на сохранённой фикстуре
реального DOM (tests/fixtures/hh_search_python.html), а HhChromeSource.fetch —
через подменённый html_fetcher (фейк без Chrome).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.domain.profile import Profile
from src.sources.base import SourceError, SourceRateLimitedError
from src.sources.hh_chrome import (
    HhChromeSource,
    _parse_salary,
    build_search_url,
    parse_vacancies,
    parse_vacancy_detail,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hh_search_python.html"
_DETAIL_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "hh_vacancy_detail.html"
)


def _fixture_html() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def _detail_html() -> str:
    return _DETAIL_FIXTURE.read_text(encoding="utf-8")


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
        "area_ids": [1],
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
# parse_vacancies на реальной фикстуре
# ============================================================================


class TestParseVacanciesFixture:
    def test_parses_all_cards(self) -> None:
        vacs = parse_vacancies(_fixture_html())
        assert len(vacs) == 8
        assert all(v.source_type == "hh" for v in vacs)
        # external_id всегда числовой (из /vacancy/{id})
        assert all(v.external_id.isdigit() for v in vacs)

    def test_first_card_fields(self) -> None:
        vacs = parse_vacancies(_fixture_html())
        v = next(v for v in vacs if v.external_id == "134003140")
        assert v.title == "IT Data Asset Intern / Стажер-менеджер по управлению данными"
        assert v.company_name == "«Procter & Gamble», Студент"
        assert v.company_id == "4949"
        assert v.area_name == "Москва"
        assert v.experience == "noExperience"
        assert v.url == "https://hh.ru/vacancy/134003140"
        # "от 100 000 ₽" → from только
        assert v.salary_from == 100000
        assert v.salary_to is None
        assert v.salary_currency == "RUR"

    def test_salary_range_card(self) -> None:
        vacs = parse_vacancies(_fixture_html())
        v = next(v for v in vacs if v.external_id == "133450153")
        assert v.salary_from == 80000
        assert v.salary_to == 100000
        assert v.salary_currency == "RUR"

    def test_card_without_salary(self) -> None:
        vacs = parse_vacancies(_fixture_html())
        v = next(v for v in vacs if v.external_id == "133521655")
        assert v.salary_from is None
        assert v.salary_to is None
        assert v.salary_currency is None

    def test_list_fields_lazy(self) -> None:
        # description / key_skills в выдаче нет — подгружаются on-demand позже.
        vacs = parse_vacancies(_fixture_html())
        assert all(v.description is None for v in vacs)
        assert all(v.key_skills == [] for v in vacs)
        assert all(v.published_at is None for v in vacs)


# ============================================================================
# Парсинг зарплатной строки (изолированно)
# ============================================================================


class TestParseSalary:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("от 100 000 ₽ за месяц, до вычета налогов", (100000, None, "RUR")),
            ("80 000 – 100 000 ₽ за месяц, на руки", (80000, 100000, "RUR")),
            ("130 000 ₽ за месяц", (130000, 130000, "RUR")),
            ("до 200 000 ₽", (None, 200000, "RUR")),
            ("от 3 000 $ за месяц", (3000, None, "USD")),
            ("", (None, None, None)),
            ("По договорённости", (None, None, None)),
        ],
    )
    def test_variants(
        self, text: str, expected: tuple[int | None, int | None, str | None]
    ) -> None:
        assert _parse_salary(text) == expected


# ============================================================================
# Детект блокировки / пустого результата
# ============================================================================


class TestBlockDetection:
    def test_challenge_page_raises_rate_limited(self) -> None:
        html = (
            "<html><head><title>Проверка</title></head><body>"
            "<div>Проверка браузера DDoS-Guard, подождите...</div>"
            "</body></html>"
        )
        with pytest.raises(SourceRateLimitedError):
            parse_vacancies(html)

    def test_legit_empty_returns_empty_list(self) -> None:
        html = (
            "<html><body><div>По вашему запросу ничего не найдено</div>"
            "</body></html>"
        )
        assert parse_vacancies(html) == []

    def test_serp_shell_without_cards_returns_empty_list(self) -> None:
        # Страница за пределами последней: оболочка выдачи есть, карточек нет,
        # текста "ничего не найдено" нет (он только на page 0). Это легальный
        # конец пагинации, а НЕ блокировка → ожидаем [].
        html = (
            '<html><body><div data-qa="vacancies-search-header">Вакансии</div>'
            '<div data-qa="vacancy-serp__results"></div></body></html>'
        )
        assert parse_vacancies(html) == []

    def test_unknown_layout_raises_source_error(self) -> None:
        html = "<html><body><div>что-то совсем другое</div></body></html>"
        with pytest.raises(SourceError):
            parse_vacancies(html)


# ============================================================================
# parse_vacancy_detail
# ============================================================================


class TestParseVacancyDetail:
    def test_extracts_description_and_skills(self) -> None:
        detail = parse_vacancy_detail(_detail_html())
        assert detail["description"] is not None
        assert "vacancy-description" in detail["description"]
        # форма key_skills: list[{"name": str}] — совместима с api/vacancies.py
        assert isinstance(detail["key_skills"], list)
        assert all("name" in s for s in detail["key_skills"])

    def test_missing_description_returns_none(self) -> None:
        detail = parse_vacancy_detail("<html><body>пусто</body></html>")
        assert detail["description"] is None
        assert detail["key_skills"] == []


# ============================================================================
# build_search_url
# ============================================================================


class TestBuildSearchUrl:
    def test_basic_params(self) -> None:
        url = build_search_url(_profile(), None, page=0)
        assert url.startswith("https://hh.ru/search/vacancy?")
        assert "text=python+fastapi" in url
        assert "area=1" in url
        assert "order_by=publication_time" in url
        assert "page=0" in url
        # salary_from=200000 → salary + only_with_salary
        assert "salary=200000" in url
        assert "only_with_salary=true" in url
        # grade НЕ маппится в фильтр опыта: hh-тег опыта ненадёжен, грейд судит LLM
        assert "experience=" not in url
        # work_format remote → work_format=REMOTE (старый schedule=remote мёртв)
        assert "work_format=REMOTE" in url

    def test_grade_does_not_filter_experience(self) -> None:
        # Грейд НЕ порождает фильтр опыта (его задаёт явное profile.experience).
        for g in ("junior", "middle", "senior", "lead"):
            url = build_search_url(_profile(grade=g, experience=[]), None, page=0)
            assert "experience=" not in url

    def test_explicit_experience_filters(self) -> None:
        # Явный выбор пользователя → фильтр по опыту (значения hh как есть).
        url = build_search_url(
            _profile(experience=["noExperience", "between1And3"]), None, page=0
        )
        assert "experience=noExperience" in url
        assert "experience=between1And3" in url

    def test_multiple_work_formats(self) -> None:
        # remote + office → два work_format= (ИЛИ), hybrid маппится тоже.
        url = build_search_url(
            _profile(work_format=["remote", "office", "hybrid"]), None, page=0
        )
        assert "work_format=REMOTE" in url
        assert "work_format=ON_SITE" in url
        assert "work_format=HYBRID" in url

    def test_multiple_areas(self) -> None:
        url = build_search_url(_profile(area_ids=[1, 2]), None, page=2)
        assert "area=1" in url
        assert "area=2" in url
        assert "page=2" in url

    def test_search_params_override(self) -> None:
        url = build_search_url(_profile(), {"text": "golang", "experience": "noExperience"}, 0)
        assert "text=golang" in url
        assert "experience=noExperience" in url


# ============================================================================
# HhChromeSource.fetch — пагинация, дедуп, без реального Chrome
# ============================================================================


@pytest.fixture(autouse=True)
def _no_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    # Убираем рандомные задержки, чтобы тесты не висели.
    from src.config import settings

    monkeypatch.setattr(settings, "parser_jitter_min_seconds", 0.0)
    monkeypatch.setattr(settings, "parser_jitter_max_seconds", 0.0)


class TestHhChromeSourceFetch:
    @pytest.mark.asyncio
    async def test_fetch_paginates_and_stops_on_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.config import settings

        monkeypatch.setattr(settings, "parser_max_pages", 5)
        fixture = _fixture_html()
        empty = "<html><body>По вашему запросу ничего не найдено</body></html>"
        calls: list[str] = []

        async def fake_fetch(url: str) -> str:
            calls.append(url)
            return fixture if "page=0" in url else empty

        source = HhChromeSource(html_fetcher=fake_fetch)
        vacs = await source.fetch(_profile())
        # page0 → 8 вакансий, page1 → пусто → стоп
        assert len(vacs) == 8
        assert len(calls) == 2  # page0 + page1(empty)

    @pytest.mark.asyncio
    async def test_fetch_dedups_across_pages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.config import settings

        monkeypatch.setattr(settings, "parser_max_pages", 3)
        fixture = _fixture_html()

        async def fake_fetch(url: str) -> str:
            return fixture  # каждая страница — те же 8 вакансий

        source = HhChromeSource(html_fetcher=fake_fetch)
        vacs = await source.fetch(_profile())
        # дубликаты по external_id отброшены → всё ещё 8, и пагинация остановилась
        assert len(vacs) == 8
        assert len({v.external_id for v in vacs}) == 8

    @pytest.mark.asyncio
    async def test_fetch_retries_then_propagates_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.config import settings

        monkeypatch.setattr(settings, "parser_chrome_max_retries", 1)
        challenge = (
            "<html><body>Подтвердите, что вы не робот (captcha)</body></html>"
        )
        attempts = 0

        async def fake_fetch(url: str) -> str:
            nonlocal attempts
            attempts += 1
            return challenge

        source = HhChromeSource(html_fetcher=fake_fetch)
        with pytest.raises(SourceRateLimitedError):
            await source.fetch(_profile())
        assert attempts == 2  # 1 попытка + 1 ретрай
