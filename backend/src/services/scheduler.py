"""In-process scheduler (APScheduler).

В v0.1 — вместо n8n. Запускается из FastAPI lifespan если PARSER_ENABLED=true.
Раз в N минут дёргает ParserService.parse_all_active() и комитит сессию.

Перенос на n8n в v0.2 — workflow вызовет тот же `parse_all_active` через
admin endpoint (или напрямую). Бизнес-логика остаётся в ParserService.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from src.config import settings
from src.db.repositories import (
    ProfileRepository,
    SourceRepository,
    VacancyRepository,
)
from src.db.session import SessionMaker
from src.services.parser import ParserService

_scheduler: AsyncIOScheduler | None = None


async def _job_parse_all() -> None:
    """Один прогон шедулера: открывает сессию, парсит все источники, коммитит."""
    async with SessionMaker() as session:
        service = ParserService(
            SourceRepository(session),
            ProfileRepository(session),
            VacancyRepository(session),
        )
        try:
            results = await service.parse_all_active()
            await session.commit()
            ok = sum(1 for r in results if r.status == "ok")
            total = len(results)
            logger.bind(ok=ok, total=total).info("scheduler: parse_all done")
        except Exception as exc:
            await session.rollback()
            logger.exception("scheduler: parse_all failed: {}", exc)


def start_scheduler() -> None:
    """Запустить шедулер. Вызывается из FastAPI lifespan."""
    global _scheduler
    if not settings.parser_enabled:
        logger.info("scheduler: PARSER_ENABLED=false, skipping")
        return
    if _scheduler is not None:
        logger.warning("scheduler: already started")
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _job_parse_all,
        trigger=IntervalTrigger(minutes=settings.parser_interval_minutes),
        id="parse_all_active",
        name="parse all active sources",
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.bind(interval=settings.parser_interval_minutes).info("scheduler: started")


def stop_scheduler() -> None:
    """Остановить шедулер. Вызывается из shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler: stopped")
