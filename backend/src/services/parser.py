"""Parser-service: оркестрация Source → БД.

Шаги:
1. Берём profile + source.
2. Дёргаем source.fetch(profile, search_params) — получаем ParsedVacancy[].
3. UPSERT в БД.
4. Обновляем source.last_status / last_parsed_at / vacancies_today.

Источники: фабрика по `source.type`. В v0.1 — только "hh".
"""

from __future__ import annotations

from loguru import logger

from src.config import settings
from src.db.repositories.profile import ProfileRepository
from src.db.repositories.source import SourceRepository
from src.db.repositories.vacancy import VacancyRepository
from src.domain.profile import Profile
from src.domain.source import ParseResult, Source
from src.sources.base import Source as SourceImpl
from src.sources.base import SourceError, SourceRateLimitedError
from src.sources.hh import HhSource
from src.sources.hh_chrome import HhChromeSource


class ParserError(Exception):
    """Базовое исключение parser-сервиса."""


class UnsupportedSourceTypeError(ParserError):
    """Source.type не реализован (например 'avito' в v0.1)."""


class SourceNotFoundError(ParserError):
    """Источник не существует или принадлежит другому юзеру."""


def get_source_impl(source_type: str) -> SourceImpl:
    """Фабрика: по строковому типу даёт реализацию Source.

    Для "hh" по умолчанию используется HhChromeSource (headless Chrome), т.к.
    публичный API hh.ru закрыт для анонимов с 15.12.2025. Старый HhSource (API)
    остаётся как аварийный путь под флагом PARSER_USE_CHROME=false.

    В v0.2 добавятся "habr", "avito" и т.п.
    """
    if source_type == "hh":
        return HhChromeSource() if settings.parser_use_chrome else HhSource()
    raise UnsupportedSourceTypeError(f"source type '{source_type}' not implemented in v0.1")


class ParserService:
    def __init__(
        self,
        sources: SourceRepository,
        profiles: ProfileRepository,
        vacancies: VacancyRepository,
    ) -> None:
        self.sources = sources
        self.profiles = profiles
        self.vacancies = vacancies

    async def parse_source(self, source: Source) -> ParseResult:
        """Парсит один источник. Не комитит — это задача вызывающего."""
        profile = await self.profiles.get_by_id(source.profile_id)
        if profile is None:
            return ParseResult(
                source_id=source.id,
                fetched=0,
                inserted=0,
                updated=0,
                status="error",
                error=f"profile {source.profile_id} not found",
            )
        return await self._parse(source, profile)

    async def _parse(self, source: Source, profile: Profile) -> ParseResult:
        try:
            impl = get_source_impl(source.type)
        except UnsupportedSourceTypeError as exc:
            await self.sources.update_parse_status(source.id, status="error", error=str(exc))
            return ParseResult(
                source_id=source.id,
                fetched=0,
                inserted=0,
                updated=0,
                status="error",
                error=str(exc),
            )

        try:
            parsed = await impl.fetch(profile, source.search_params)
        except SourceRateLimitedError as exc:
            logger.bind(source_id=source.id).warning("parser: rate limited")
            await self.sources.update_parse_status(source.id, status="rate_limited", error=str(exc))
            return ParseResult(
                source_id=source.id,
                fetched=0,
                inserted=0,
                updated=0,
                status="rate_limited",
                error=str(exc),
            )
        except SourceError as exc:
            logger.bind(source_id=source.id).error("parser: source error: {}", exc)
            await self.sources.update_parse_status(source.id, status="error", error=str(exc))
            return ParseResult(
                source_id=source.id,
                fetched=0,
                inserted=0,
                updated=0,
                status="error",
                error=str(exc),
            )

        inserted, updated = await self.vacancies.upsert_many(parsed)
        # Заменяем набор вакансий источника на свежий результат: лента покажет
        # только эту выдачу, а не накопленное старьё (важно при смене фильтров).
        await self.vacancies.set_source_links(source.id, parsed)
        await self.sources.update_parse_status(
            source.id, status="ok", vacancies_today_delta=inserted
        )
        logger.bind(
            source_id=source.id,
            fetched=len(parsed),
            inserted=inserted,
            updated=updated,
        ).info("parser: ok")
        return ParseResult(
            source_id=source.id,
            fetched=len(parsed),
            inserted=inserted,
            updated=updated,
            status="ok",
        )

    async def parse_for_user(self, source_id: int, user_id: int) -> ParseResult:
        """Ручной refresh — пользователь дёрнул POST /sources/{id}/refresh."""
        source = await self.sources.get_by_id_for_user(source_id, user_id)
        if source is None:
            raise SourceNotFoundError(f"source {source_id} not found")
        return await self.parse_source(source)

    async def parse_all_active(self) -> list[ParseResult]:
        """Используется шедулером. Парсит все активные источники подряд."""
        results: list[ParseResult] = []
        for source in await self.sources.list_active():
            try:
                results.append(await self.parse_source(source))
            except Exception as exc:
                logger.bind(source_id=source.id).exception("parser: unexpected error: {}", exc)
                results.append(
                    ParseResult(
                        source_id=source.id,
                        fetched=0,
                        inserted=0,
                        updated=0,
                        status="error",
                        error=str(exc),
                    )
                )
        return results
