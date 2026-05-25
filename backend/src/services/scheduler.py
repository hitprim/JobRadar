"""In-process scheduler (APScheduler).

В v0.1 — вместо n8n. Запускается из FastAPI lifespan если PARSER_ENABLED=true.
Три job'а под одним флагом:
- parse_all_active: каждые PARSER_INTERVAL_MINUTES дёргает hh.ru
- vacancy_alerts: каждые ALERTS_INTERVAL_MINUTES шлёт count новых вакансий
- send_reminders: каждые REMINDERS_INTERVAL_MINUTES шлёт due-reminders

Перенос на n8n в v0.2 — workflow вызовет те же бизнес-методы через admin endpoint.
"""

from __future__ import annotations

from datetime import timedelta

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
from src.services.notifications import NotificationsService
from src.services.parser import ParserService

_scheduler: AsyncIOScheduler | None = None


async def _job_parse_all() -> None:
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
            logger.bind(ok=ok, total=len(results)).info("scheduler: parse_all done")
        except Exception as exc:
            await session.rollback()
            logger.exception("scheduler: parse_all failed: {}", exc)


async def _job_vacancy_alerts() -> None:
    """Шлёт alerts о новых вакансиях за последние PARSER_INTERVAL_MINUTES.

    Lookback совпадает с интервалом самого alerts-job'а (см. start_scheduler),
    чтобы не было пропусков и дублей.
    """
    async with SessionMaker() as session:
        svc = NotificationsService(session)
        try:
            await svc.run_vacancy_alerts(
                lookback=timedelta(minutes=settings.alerts_interval_minutes)
            )
        except Exception as exc:
            logger.exception("scheduler: vacancy_alerts failed: {}", exc)
        finally:
            await svc.aclose()


async def _job_reminders() -> None:
    async with SessionMaker() as session:
        svc = NotificationsService(session)
        try:
            await svc.run_reminders()
        except Exception as exc:
            await session.rollback()
            logger.exception("scheduler: reminders failed: {}", exc)
        finally:
            await svc.aclose()


def start_scheduler() -> None:
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
        coalesce=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _job_vacancy_alerts,
        trigger=IntervalTrigger(minutes=settings.alerts_interval_minutes),
        id="vacancy_alerts",
        coalesce=True,
        max_instances=1,
    )
    _scheduler.add_job(
        _job_reminders,
        trigger=IntervalTrigger(minutes=settings.reminders_interval_minutes),
        id="send_reminders",
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.bind(
        parse_every=settings.parser_interval_minutes,
        alerts_every=settings.alerts_interval_minutes,
        reminders_every=settings.reminders_interval_minutes,
    ).info("scheduler: started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler: stopped")
