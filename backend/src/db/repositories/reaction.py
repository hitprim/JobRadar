"""Repository для vacancy_reactions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models import Profile as ProfileORM
from src.db.models import Vacancy as VacancyORM
from src.db.models import VacancyReaction as ReactionORM
from src.db.repositories.base import BaseRepository
from src.domain.vacancy import VacancyReaction


def _to_domain(orm: ReactionORM) -> VacancyReaction:
    return VacancyReaction(
        id=orm.id,
        profile_id=orm.profile_id,
        vacancy_id=orm.vacancy_id,
        reaction=orm.reaction,
        score=orm.score,
        score_reason=orm.score_reason,
        red_flags=list(orm.red_flags or []),
        scored_at=orm.scored_at,
    )


class ReactionRepository(BaseRepository):
    async def get(self, *, profile_id: int, vacancy_id: int) -> VacancyReaction | None:
        stmt = select(ReactionORM).where(
            ReactionORM.profile_id == profile_id,
            ReactionORM.vacancy_id == vacancy_id,
        )
        orm = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def upsert_reaction(
        self,
        *,
        profile_id: int,
        vacancy_id: int,
        reaction: str,
    ) -> VacancyReaction:
        """UPSERT реакции (like / skip / save)."""
        stmt = (
            pg_insert(ReactionORM)
            .values(profile_id=profile_id, vacancy_id=vacancy_id, reaction=reaction)
            .on_conflict_do_update(
                constraint="uq_reactions_profile_vacancy",
                set_={"reaction": reaction},
            )
            .returning(ReactionORM)
        )
        orm = (await self.session.execute(stmt)).scalar_one()
        return _to_domain(orm)

    async def profile_belongs_to_user(self, profile_id: int, user_id: int) -> bool:
        """Helper: проверка принадлежности профиля юзеру (для защиты от IDOR)."""
        stmt = select(ProfileORM.id).where(
            ProfileORM.id == profile_id, ProfileORM.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def vacancy_exists(self, vacancy_id: int) -> bool:
        stmt = select(VacancyORM.id).where(VacancyORM.id == vacancy_id)
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None
