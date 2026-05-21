"""Repository для sources."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from src.db.models import Profile as ProfileORM
from src.db.models import Source as SourceORM
from src.db.repositories.base import BaseRepository
from src.domain.source import Source, SourceCreate


def _to_domain(orm: SourceORM) -> Source:
    return Source(
        id=orm.id,
        profile_id=orm.profile_id,
        type=orm.type,  # type: ignore[arg-type]
        search_params=orm.search_params,
        is_active=orm.is_active,
        last_parsed_at=orm.last_parsed_at,
        last_status=orm.last_status,
        last_error=orm.last_error,
        vacancies_today=orm.vacancies_today,
    )


class SourceRepository(BaseRepository):
    async def get_by_id(self, source_id: int) -> Source | None:
        orm = await self.session.get(SourceORM, source_id)
        return _to_domain(orm) if orm else None

    async def get_by_id_for_user(self, source_id: int, user_id: int) -> Source | None:
        """Возвращает source только если его profile принадлежит юзеру (защита от IDOR)."""
        stmt = (
            select(SourceORM)
            .join(ProfileORM, SourceORM.profile_id == ProfileORM.id)
            .where(SourceORM.id == source_id, ProfileORM.user_id == user_id)
        )
        orm = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_profile(self, profile_id: int) -> list[Source]:
        stmt = (
            select(SourceORM).where(SourceORM.profile_id == profile_id).order_by(SourceORM.id.asc())
        )
        result = await self.session.execute(stmt)
        return [_to_domain(orm) for orm in result.scalars().all()]

    async def create(self, profile_id: int, data: SourceCreate) -> Source:
        orm = SourceORM(
            profile_id=profile_id,
            type=data.type,
            search_params=data.search_params,
            is_active=True,
        )
        self.session.add(orm)
        await self.session.flush()
        return _to_domain(orm)

    async def delete_for_user(self, source_id: int, user_id: int) -> bool:
        """Удаляет source если его profile принадлежит юзеру."""
        source = await self.get_by_id_for_user(source_id, user_id)
        if source is None:
            return False
        orm = await self.session.get(SourceORM, source_id)
        if orm is None:
            return False
        await self.session.delete(orm)
        return True

    async def update_parse_status(
        self,
        source_id: int,
        *,
        status: str,
        error: str | None = None,
        vacancies_today_delta: int = 0,
    ) -> None:
        orm = await self.session.get(SourceORM, source_id)
        if orm is None:
            return
        orm.last_parsed_at = datetime.now(UTC)
        orm.last_status = status
        orm.last_error = error
        orm.vacancies_today = (orm.vacancies_today or 0) + vacancies_today_delta

    async def list_active(self) -> list[Source]:
        """Все активные источники (для шедулера)."""
        stmt = select(SourceORM).where(SourceORM.is_active.is_(True))
        result = await self.session.execute(stmt)
        return [_to_domain(orm) for orm in result.scalars().all()]
