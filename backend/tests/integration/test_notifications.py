"""Integration-тесты NotificationsService — без реальных Telegram-запросов.

Bot мокаем через monkeypatch.setattr(NotificationsService, '_build_bot', ...)
и подсчитываем кому что отправлено.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Application as ApplicationORM
from src.db.models import Profile as ProfileORM
from src.db.models import Source as SourceORM
from src.db.models import User as UserORM
from src.db.models import Vacancy as VacancyORM
from src.security.encryption import generate_dek, wrap_dek
from src.services.notifications import NotificationsService

pytestmark = pytest.mark.asyncio


class _FakeBot:
    """Минимальный мок aiogram.Bot — записывает все send_message."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail_for_telegram_id: int | None = None

    async def send_message(self, *, chat_id: int, text: str, reply_markup: Any = None) -> None:
        if self.fail_for_telegram_id is not None and chat_id == self.fail_for_telegram_id:
            from aiogram.exceptions import TelegramAPIError

            raise TelegramAPIError(method=None, message="fake error")  # type: ignore[arg-type]
        self.sent.append({"chat_id": chat_id, "text": text})

    class _Session:
        async def close(self) -> None: ...

    @property
    def session(self) -> _Session:
        return _FakeBot._Session()


@pytest.fixture
def fake_bot() -> _FakeBot:
    return _FakeBot()


async def _make_user_with_profile_and_source(
    session: AsyncSession, *, telegram_id: int, notifications_enabled: bool = True
) -> UserORM:
    user = UserORM(
        telegram_id=telegram_id,
        first_name="T",
        dek_encrypted=wrap_dek(generate_dek()),
        notifications_enabled=notifications_enabled,
    )
    session.add(user)
    await session.flush()
    profile = ProfileORM(
        user_id=user.id,
        name="P",
        category="it",
        is_active=True,
    )
    session.add(profile)
    await session.flush()
    source = SourceORM(profile_id=profile.id, type="hh", is_active=True)
    session.add(source)
    await session.commit()
    await session.refresh(user)
    return user


async def _seed_vacancy(
    session: AsyncSession,
    *,
    external_id: str,
    parsed_at: datetime,
) -> VacancyORM:
    v = VacancyORM(
        external_id=external_id,
        source_type="hh",
        title="Test vacancy",
        parsed_at=parsed_at,
        published_at=parsed_at,
    )
    session.add(v)
    await session.commit()
    await session.refresh(v)
    return v


# ============================================================================
# Vacancy alerts
# ============================================================================


class TestVacancyAlerts:
    async def test_finds_users_with_new_vacancies(
        self, db_session: AsyncSession, fake_bot: _FakeBot
    ) -> None:
        u1 = await _make_user_with_profile_and_source(db_session, telegram_id=111)
        u2 = await _make_user_with_profile_and_source(db_session, telegram_id=222)
        now = datetime.now(UTC)
        await _seed_vacancy(db_session, external_id="v1", parsed_at=now - timedelta(minutes=10))
        await _seed_vacancy(db_session, external_id="v2", parsed_at=now - timedelta(minutes=5))

        svc = NotificationsService(db_session, bot=fake_bot)  # type: ignore[arg-type]
        alerts = await svc.find_vacancy_alerts(now - timedelta(hours=1))
        # Оба юзера должны получить — у обоих по одному hh-source
        tg_ids = sorted(a.telegram_id for a in alerts)
        assert tg_ids == [111, 222]
        # У каждого по 2 новых вакансии
        for a in alerts:
            assert a.new_count == 2

        sent = await svc.run_vacancy_alerts(lookback=timedelta(hours=1))
        assert sent == 2
        assert len(fake_bot.sent) == 2
        # text содержит count
        assert "2" in fake_bot.sent[0]["text"]
        # Не использовали u1.id напрямую (только telegram_id):
        _ = u1.id
        _ = u2.id

    async def test_skips_unsubscribed_users(
        self, db_session: AsyncSession, fake_bot: _FakeBot
    ) -> None:
        await _make_user_with_profile_and_source(
            db_session, telegram_id=333, notifications_enabled=False
        )
        now = datetime.now(UTC)
        await _seed_vacancy(db_session, external_id="v1", parsed_at=now)

        svc = NotificationsService(db_session, bot=fake_bot)  # type: ignore[arg-type]
        alerts = await svc.find_vacancy_alerts(now - timedelta(hours=1))
        assert alerts == []

    async def test_skips_users_without_sources(
        self, db_session: AsyncSession, fake_bot: _FakeBot
    ) -> None:
        # Юзер с профилем без источников
        user = UserORM(
            telegram_id=444,
            first_name="X",
            dek_encrypted=wrap_dek(generate_dek()),
        )
        db_session.add(user)
        await db_session.flush()
        profile = ProfileORM(user_id=user.id, name="P", category="it")
        db_session.add(profile)
        await db_session.commit()

        now = datetime.now(UTC)
        await _seed_vacancy(db_session, external_id="v1", parsed_at=now)

        svc = NotificationsService(db_session, bot=fake_bot)  # type: ignore[arg-type]
        alerts = await svc.find_vacancy_alerts(now - timedelta(hours=1))
        assert alerts == []

    async def test_failed_send_doesnt_break(
        self, db_session: AsyncSession, fake_bot: _FakeBot
    ) -> None:
        await _make_user_with_profile_and_source(db_session, telegram_id=555)
        await _make_user_with_profile_and_source(db_session, telegram_id=666)
        now = datetime.now(UTC)
        await _seed_vacancy(db_session, external_id="v1", parsed_at=now)

        fake_bot.fail_for_telegram_id = 555

        svc = NotificationsService(db_session, bot=fake_bot)  # type: ignore[arg-type]
        sent = await svc.run_vacancy_alerts(lookback=timedelta(hours=1))
        # один упал — но не сломал второго
        assert sent == 1
        assert len(fake_bot.sent) == 1
        assert fake_bot.sent[0]["chat_id"] == 666


# ============================================================================
# Reminders
# ============================================================================


class TestReminders:
    async def test_sends_due_reminder_and_marks_sent(
        self, db_session: AsyncSession, fake_bot: _FakeBot
    ) -> None:
        user = await _make_user_with_profile_and_source(db_session, telegram_id=777)
        vacancy = await _seed_vacancy(db_session, external_id="vr", parsed_at=datetime.now(UTC))
        # Создаём application с прошедшим reminder_at
        profile = (
            await db_session.execute(
                ProfileORM.__table__.select().where(ProfileORM.user_id == user.id)
            )
        ).first()
        assert profile is not None
        past = datetime.now(UTC) - timedelta(hours=1)
        app = ApplicationORM(
            profile_id=profile.id,
            vacancy_id=vacancy.id,
            status="sent",
            notes="Напомнить через час",
            next_reminder_at=past,
        )
        db_session.add(app)
        await db_session.commit()
        await db_session.refresh(app)

        svc = NotificationsService(db_session, bot=fake_bot)  # type: ignore[arg-type]
        sent = await svc.run_reminders()
        assert sent == 1
        assert len(fake_bot.sent) == 1
        assert "777" not in fake_bot.sent[0]["text"]  # chat_id передаётся отдельно
        assert fake_bot.sent[0]["chat_id"] == 777
        assert "Напомнить через час" in fake_bot.sent[0]["text"]

        # next_reminder_at сброшен, reminder_sent_at установлен
        await db_session.refresh(app)
        assert app.next_reminder_at is None
        assert app.reminder_sent_at is not None

    async def test_skips_future_reminders(
        self, db_session: AsyncSession, fake_bot: _FakeBot
    ) -> None:
        user = await _make_user_with_profile_and_source(db_session, telegram_id=888)
        vacancy = await _seed_vacancy(db_session, external_id="vf", parsed_at=datetime.now(UTC))
        profile = (
            await db_session.execute(
                ProfileORM.__table__.select().where(ProfileORM.user_id == user.id)
            )
        ).first()
        assert profile is not None
        future = datetime.now(UTC) + timedelta(days=1)
        app = ApplicationORM(
            profile_id=profile.id,
            vacancy_id=vacancy.id,
            status="sent",
            next_reminder_at=future,
        )
        db_session.add(app)
        await db_session.commit()

        svc = NotificationsService(db_session, bot=fake_bot)  # type: ignore[arg-type]
        tasks = await svc.find_pending_reminders()
        assert tasks == []

    async def test_skips_unsubscribed_user_reminder(
        self, db_session: AsyncSession, fake_bot: _FakeBot
    ) -> None:
        user = await _make_user_with_profile_and_source(
            db_session, telegram_id=999, notifications_enabled=False
        )
        vacancy = await _seed_vacancy(db_session, external_id="vu", parsed_at=datetime.now(UTC))
        profile = (
            await db_session.execute(
                ProfileORM.__table__.select().where(ProfileORM.user_id == user.id)
            )
        ).first()
        assert profile is not None
        app = ApplicationORM(
            profile_id=profile.id,
            vacancy_id=vacancy.id,
            status="sent",
            next_reminder_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db_session.add(app)
        await db_session.commit()

        svc = NotificationsService(db_session, bot=fake_bot)  # type: ignore[arg-type]
        tasks = await svc.find_pending_reminders()
        assert tasks == []

    async def test_reenable_subscription_via_db(
        self, db_session: AsyncSession, fake_bot: _FakeBot
    ) -> None:
        # Симулируем: юзер сделал /notifications off потом /start (вернул on)
        await _make_user_with_profile_and_source(
            db_session, telegram_id=1010, notifications_enabled=False
        )
        await db_session.execute(
            update(UserORM).where(UserORM.telegram_id == 1010).values(notifications_enabled=True)
        )
        await db_session.commit()

        now = datetime.now(UTC)
        await _seed_vacancy(db_session, external_id="vrr", parsed_at=now)

        svc = NotificationsService(db_session, bot=fake_bot)  # type: ignore[arg-type]
        alerts = await svc.find_vacancy_alerts(now - timedelta(hours=1))
        assert len(alerts) == 1
        assert alerts[0].telegram_id == 1010
