"""Repository для letters."""

from __future__ import annotations

from sqlalchemy import select, update

from src.db.models import Letter as LetterORM
from src.db.models import Profile as ProfileORM
from src.db.repositories.base import BaseRepository
from src.domain.letter import Letter


def _to_domain(orm: LetterORM) -> Letter:
    return Letter(
        id=orm.id,
        profile_id=orm.profile_id,
        vacancy_id=orm.vacancy_id,
        text=orm.text,
        prompt_used=orm.prompt_used,
        used_in_application=orm.used_in_application,
        created_at=orm.created_at,
    )


class LetterRepository(BaseRepository):
    async def get_by_id(self, letter_id: int) -> Letter | None:
        orm = await self.session.get(LetterORM, letter_id)
        return _to_domain(orm) if orm else None

    async def get_by_id_for_user(self, letter_id: int, user_id: int) -> Letter | None:
        """Возвращает письмо только если его profile принадлежит юзеру."""
        stmt = (
            select(LetterORM)
            .join(ProfileORM, LetterORM.profile_id == ProfileORM.id)
            .where(LetterORM.id == letter_id, ProfileORM.user_id == user_id)
        )
        orm = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def list_for_profile(
        self, profile_id: int, *, limit: int = 50, offset: int = 0
    ) -> list[Letter]:
        stmt = (
            select(LetterORM)
            .where(LetterORM.profile_id == profile_id)
            .order_by(LetterORM.created_at.desc(), LetterORM.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [_to_domain(orm) for orm in result.scalars().all()]

    async def create(
        self,
        *,
        profile_id: int,
        vacancy_id: int,
        text: str,
        prompt_used: str | None,
    ) -> Letter:
        orm = LetterORM(
            profile_id=profile_id,
            vacancy_id=vacancy_id,
            text=text,
            prompt_used=prompt_used,
            used_in_application=False,
        )
        self.session.add(orm)
        await self.session.flush()
        return _to_domain(orm)

    async def update_for_user(
        self,
        letter_id: int,
        user_id: int,
        *,
        text: str | None = None,
        used_in_application: bool | None = None,
    ) -> Letter | None:
        # Сначала проверяем что письмо наше
        existing = await self.get_by_id_for_user(letter_id, user_id)
        if existing is None:
            return None
        values: dict = {}
        if text is not None:
            values["text"] = text
        if used_in_application is not None:
            values["used_in_application"] = used_in_application
        if not values:
            return existing
        stmt = (
            update(LetterORM).where(LetterORM.id == letter_id).values(**values).returning(LetterORM)
        )
        orm = (await self.session.execute(stmt)).scalar_one()
        return _to_domain(orm)
