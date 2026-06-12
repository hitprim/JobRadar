"""Repository для шаблонов сопроводительных (letter_templates)."""

from __future__ import annotations

from sqlalchemy import delete, select, update

from src.db.models import LetterTemplate as LetterTemplateORM
from src.db.models import Profile as ProfileORM
from src.db.repositories.base import BaseRepository
from src.domain.letter_template import LetterTemplate


def _to_domain(orm: LetterTemplateORM) -> LetterTemplate:
    return LetterTemplate(
        id=orm.id,
        profile_id=orm.profile_id,
        title=orm.title,
        body=orm.body,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class LetterTemplateRepository(BaseRepository):
    async def list_for_profile(self, profile_id: int) -> list[LetterTemplate]:
        stmt = (
            select(LetterTemplateORM)
            .where(LetterTemplateORM.profile_id == profile_id)
            .order_by(LetterTemplateORM.updated_at.desc(), LetterTemplateORM.id.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_to_domain(o) for o in rows]

    async def get_for_user(self, template_id: int, user_id: int) -> LetterTemplate | None:
        """Шаблон только если его профиль принадлежит юзеру."""
        stmt = (
            select(LetterTemplateORM)
            .join(ProfileORM, LetterTemplateORM.profile_id == ProfileORM.id)
            .where(LetterTemplateORM.id == template_id, ProfileORM.user_id == user_id)
        )
        orm = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def create(self, *, profile_id: int, title: str, body: str) -> LetterTemplate:
        orm = LetterTemplateORM(profile_id=profile_id, title=title, body=body)
        self.session.add(orm)
        await self.session.flush()
        return _to_domain(orm)

    async def update(
        self,
        template_id: int,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> LetterTemplate:
        values: dict = {}
        if title is not None:
            values["title"] = title
        if body is not None:
            values["body"] = body
        stmt = (
            update(LetterTemplateORM)
            .where(LetterTemplateORM.id == template_id)
            .values(**values)
            .returning(LetterTemplateORM)
        )
        orm = (await self.session.execute(stmt)).scalar_one()
        return _to_domain(orm)

    async def delete(self, template_id: int) -> None:
        await self.session.execute(
            delete(LetterTemplateORM).where(LetterTemplateORM.id == template_id)
        )
