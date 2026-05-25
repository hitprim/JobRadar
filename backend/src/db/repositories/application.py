"""Repository для applications + status_history + funnel-запросы."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from src.db.models import Application as ApplicationORM
from src.db.models import ApplicationStatusHistory as HistoryORM
from src.db.models import Profile as ProfileORM
from src.db.models import Vacancy as VacancyORM
from src.db.repositories.base import BaseRepository
from src.domain.application import (
    APPLICATION_STATUSES,
    Application,
    ApplicationCreate,
    ApplicationStatusHistory,
    ApplicationUpdate,
    FunnelStats,
)


class DuplicateApplicationError(Exception):
    """Application для этой пары (profile_id, vacancy_id) уже существует."""

    def __init__(self, existing_id: int) -> None:
        super().__init__(f"application for this vacancy already exists (id={existing_id})")
        self.existing_id = existing_id


def _to_domain(orm: ApplicationORM) -> Application:
    return Application(
        id=orm.id,
        profile_id=orm.profile_id,
        vacancy_id=orm.vacancy_id,
        status=orm.status,  # type: ignore[arg-type]
        cover_letter=orm.cover_letter,
        notes=orm.notes,
        next_reminder_at=orm.next_reminder_at,
        reminder_sent_at=orm.reminder_sent_at,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def _history_to_domain(orm: HistoryORM) -> ApplicationStatusHistory:
    return ApplicationStatusHistory(
        id=orm.id,
        application_id=orm.application_id,
        status=orm.status,  # type: ignore[arg-type]
        changed_at=orm.changed_at,
    )


class ApplicationRepository(BaseRepository):
    async def get_by_id(self, application_id: int) -> Application | None:
        orm = await self.session.get(ApplicationORM, application_id)
        return _to_domain(orm) if orm else None

    async def get_by_id_for_user(self, application_id: int, user_id: int) -> Application | None:
        """IDOR-защита через profiles.user_id."""
        stmt = (
            select(ApplicationORM)
            .join(ProfileORM, ApplicationORM.profile_id == ProfileORM.id)
            .where(ApplicationORM.id == application_id, ProfileORM.user_id == user_id)
        )
        orm = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def get_by_profile_vacancy(self, profile_id: int, vacancy_id: int) -> Application | None:
        stmt = select(ApplicationORM).where(
            ApplicationORM.profile_id == profile_id,
            ApplicationORM.vacancy_id == vacancy_id,
        )
        orm = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_profile(
        self, profile_id: int, *, limit: int = 100, offset: int = 0
    ) -> list[Application]:
        stmt = (
            select(ApplicationORM)
            .where(ApplicationORM.profile_id == profile_id)
            .order_by(ApplicationORM.created_at.desc(), ApplicationORM.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [_to_domain(orm) for orm in result.scalars().all()]

    async def vacancy_exists(self, vacancy_id: int) -> bool:
        stmt = select(VacancyORM.id).where(VacancyORM.id == vacancy_id)
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def create(self, profile_id: int, data: ApplicationCreate) -> Application:
        """Создаёт application + запись 'sent' в history.

        Raises:
            DuplicateApplicationError: если уже есть application для этой пары.
        """
        orm = ApplicationORM(
            profile_id=profile_id,
            vacancy_id=data.vacancy_id,
            status="sent",
            cover_letter=data.cover_letter,
            notes=data.notes,
            next_reminder_at=data.next_reminder_at,
        )
        self.session.add(orm)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.get_by_profile_vacancy(profile_id, data.vacancy_id)
            if existing is not None:
                raise DuplicateApplicationError(existing.id) from exc
            raise

        # История: начальный статус 'sent'
        history_orm = HistoryORM(application_id=orm.id, status="sent")
        self.session.add(history_orm)
        await self.session.flush()

        return _to_domain(orm)

    async def update_for_user(
        self,
        application_id: int,
        user_id: int,
        data: ApplicationUpdate,
    ) -> tuple[Application | None, bool]:
        """Обновляет application. Возвращает (app, status_changed).

        status_changed=True означает что status поменялся и нужно писать в history.
        Запись в history делает caller (service), чтобы изолировать SQL от логики.
        """
        existing = await self.get_by_id_for_user(application_id, user_id)
        if existing is None:
            return None, False

        patch = data.model_dump(exclude_unset=True)
        if not patch:
            return existing, False

        status_changed = "status" in patch and patch["status"] != existing.status

        stmt = (
            update(ApplicationORM)
            .where(ApplicationORM.id == application_id)
            .values(**patch)
            .returning(ApplicationORM)
        )
        orm = (await self.session.execute(stmt)).scalar_one()
        return _to_domain(orm), status_changed

    async def add_status_history(
        self, application_id: int, status: str
    ) -> ApplicationStatusHistory:
        orm = HistoryORM(application_id=application_id, status=status)
        self.session.add(orm)
        await self.session.flush()
        return _history_to_domain(orm)

    async def list_history(self, application_id: int) -> list[ApplicationStatusHistory]:
        stmt = (
            select(HistoryORM)
            .where(HistoryORM.application_id == application_id)
            .order_by(HistoryORM.changed_at.asc(), HistoryORM.id.asc())
        )
        result = await self.session.execute(stmt)
        return [_history_to_domain(orm) for orm in result.scalars().all()]

    async def funnel_for_profile(self, profile_id: int) -> FunnelStats:
        """GROUP BY status — counts по current status профиля.

        Возвращает все 6 статусов с нулями (для предсказуемого UI).
        Conversion rates вычисляются от total (если total>0).
        """
        stmt = (
            select(ApplicationORM.status, func.count(ApplicationORM.id))
            .where(ApplicationORM.profile_id == profile_id)
            .group_by(ApplicationORM.status)
        )
        rows = (await self.session.execute(stmt)).all()
        counts: dict[str, int] = {s: 0 for s in APPLICATION_STATUSES}
        for status, count in rows:
            if status in counts:
                counts[status] = int(count)
            # неизвестные статусы игнорируем (legacy/мусор)

        total = sum(counts.values())
        rates: dict[str, float] = {}
        if total > 0:
            for s, c in counts.items():
                rates[s] = round(c / total, 4)
        else:
            for s in counts:
                rates[s] = 0.0

        return FunnelStats(total=total, counts=counts, conversion_rates=rates)
