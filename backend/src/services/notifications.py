"""NotificationsService: рассылка через Telegram bot.

Не зависит от aiogram Dispatcher — создаёт свой Bot-инстанс по требованию.
Так scheduler может работать в одном процессе с FastAPI без поднятия dispatcher.

Job'ы:
- vacancy_alerts: для каждого юзера с notifications_enabled — сколько новых
  вакансий появилось за последний интервал, шлём count + кнопку "Открыть ленту".
- send_reminders: applications с next_reminder_at <= now() AND reminder_sent_at
  IS NULL — шлём напоминание, сбрасываем next_reminder_at = NULL, ставим
  reminder_sent_at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import Application as ApplicationORM
from src.db.models import Profile as ProfileORM
from src.db.models import Source as SourceORM
from src.db.models import User as UserORM
from src.db.models import Vacancy as VacancyORM


@dataclass(frozen=True)
class VacancyAlert:
    telegram_id: int
    new_count: int


@dataclass(frozen=True)
class ReminderTask:
    telegram_id: int
    application_id: int
    notes: str | None


def _miniapp_keyboard() -> InlineKeyboardMarkup | None:
    if not settings.miniapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть JobRadar",
                    web_app=WebAppInfo(url=settings.miniapp_url),
                )
            ]
        ]
    )


class NotificationsService:
    """Бизнес-логика рассылки. SQL-запросы — здесь же (тонкие и однотипные)."""

    def __init__(self, session: AsyncSession, bot: Bot | None = None) -> None:
        self.session = session
        self._bot = bot
        self._owns_bot = bot is None

    def _build_bot(self) -> Bot:
        if self._bot is not None:
            return self._bot
        self._bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        return self._bot

    async def aclose(self) -> None:
        if self._owns_bot and self._bot is not None:
            await self._bot.session.close()
            self._bot = None

    # ------------------------------------------------------------------
    # Vacancy alerts
    # ------------------------------------------------------------------
    async def find_vacancy_alerts(self, since: datetime) -> list[VacancyAlert]:
        """Для каждого юзера с notifications_enabled считаем сколько новых
        вакансий появилось с `since` и есть ли у его профилей такие источники.

        Считаем: count(distinct vacancy.id) где vacancy.source_type in (source.type
        for source in user.profiles[*].sources) AND vacancy.parsed_at >= since.
        """
        stmt = (
            select(
                UserORM.telegram_id,
                func.count(func.distinct(VacancyORM.id)).label("cnt"),
            )
            .select_from(UserORM)
            .join(ProfileORM, ProfileORM.user_id == UserORM.id)
            .join(SourceORM, SourceORM.profile_id == ProfileORM.id)
            .join(VacancyORM, VacancyORM.source_type == SourceORM.type)
            .where(
                UserORM.notifications_enabled.is_(True),
                ProfileORM.is_active.is_(True),
                SourceORM.is_active.is_(True),
                VacancyORM.parsed_at >= since,
            )
            .group_by(UserORM.telegram_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return [VacancyAlert(telegram_id=r[0], new_count=int(r[1])) for r in rows if r[1] > 0]

    async def send_vacancy_alert(self, alert: VacancyAlert) -> bool:
        """Отправляет одно уведомление. True при успехе."""
        bot = self._build_bot()
        text = (
            f"🔔 Найдено новых вакансий: <b>{alert.new_count}</b>\n\n"
            f"Откройте ленту, чтобы посмотреть подходящие."
        )
        try:
            await bot.send_message(
                chat_id=alert.telegram_id,
                text=text,
                reply_markup=_miniapp_keyboard(),
            )
            return True
        except TelegramAPIError as exc:
            logger.bind(telegram_id=alert.telegram_id, error=str(exc)).warning(
                "notifications: failed to send vacancy alert"
            )
            return False

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------
    async def find_pending_reminders(self, now: datetime | None = None) -> list[ReminderTask]:
        now = now or datetime.now(UTC)
        stmt = (
            select(
                ApplicationORM.id,
                ApplicationORM.notes,
                UserORM.telegram_id,
                UserORM.notifications_enabled,
            )
            .select_from(ApplicationORM)
            .join(ProfileORM, ProfileORM.id == ApplicationORM.profile_id)
            .join(UserORM, UserORM.id == ProfileORM.user_id)
            .where(
                ApplicationORM.next_reminder_at.is_not(None),
                ApplicationORM.next_reminder_at <= now,
                UserORM.notifications_enabled.is_(True),
            )
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            ReminderTask(telegram_id=r[2], application_id=r[0], notes=r[1])
            for r in rows
            if r[3]  # notifications_enabled
        ]

    async def send_reminder(self, task: ReminderTask) -> bool:
        bot = self._build_bot()
        notes_block = f"\n\n<i>Заметка:</i> {task.notes}" if task.notes else ""
        text = (
            f"⏰ Напоминание про отклик #{task.application_id}.\n"
            f"Проверьте статус и обновите его в трекере."
            f"{notes_block}"
        )
        try:
            await bot.send_message(
                chat_id=task.telegram_id,
                text=text,
                reply_markup=_miniapp_keyboard(),
            )
            return True
        except TelegramAPIError as exc:
            logger.bind(application_id=task.application_id, error=str(exc)).warning(
                "notifications: failed to send reminder"
            )
            return False

    async def mark_reminder_sent(self, application_id: int) -> None:
        """Сбрасывает next_reminder_at и пишет reminder_sent_at = now()."""
        await self.session.execute(
            update(ApplicationORM)
            .where(ApplicationORM.id == application_id)
            .values(
                next_reminder_at=None,
                reminder_sent_at=datetime.now(UTC),
            )
        )

    # ------------------------------------------------------------------
    # Job-runners (с коммитом сессии)
    # ------------------------------------------------------------------
    async def run_vacancy_alerts(self, *, lookback: timedelta) -> int:
        """Прогоняет alerts за последние `lookback`. Возвращает кол-во отправленных."""
        since = datetime.now(UTC) - lookback
        alerts = await self.find_vacancy_alerts(since)
        sent = 0
        for a in alerts:
            if await self.send_vacancy_alert(a):
                sent += 1
        logger.bind(found=len(alerts), sent=sent).info("notifications: vacancy alerts done")
        return sent

    async def run_reminders(self) -> int:
        tasks = await self.find_pending_reminders()
        sent = 0
        for t in tasks:
            if await self.send_reminder(t):
                await self.mark_reminder_sent(t.application_id)
                sent += 1
        await self.session.commit()
        logger.bind(found=len(tasks), sent=sent).info("notifications: reminders done")
        return sent
