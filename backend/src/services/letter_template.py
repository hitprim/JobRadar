"""Сервис шаблонов сопроводительных.

Тонкая бизнес-логика: проверка владения профилем/шаблоном (IDOR) поверх
repository. Подстановка плейсхолдеров делается на клиенте — здесь только CRUD.
"""

from __future__ import annotations

from src.db.repositories.letter_template import LetterTemplateRepository
from src.db.repositories.profile import ProfileRepository
from src.domain.letter_template import LetterTemplate


class ProfileNotAccessibleError(Exception):
    """Профиль не принадлежит юзеру (или не существует)."""


class TemplateNotFoundError(Exception):
    """Шаблон не найден или не принадлежит юзеру."""


class LetterTemplateService:
    def __init__(
        self,
        templates: LetterTemplateRepository,
        profiles: ProfileRepository,
    ) -> None:
        self.templates = templates
        self.profiles = profiles

    async def list_for_profile(
        self, profile_id: int, user_id: int
    ) -> list[LetterTemplate]:
        if await self.profiles.get_by_id_for_user(profile_id, user_id) is None:
            raise ProfileNotAccessibleError("profile not found")
        return await self.templates.list_for_profile(profile_id)

    async def create(
        self, profile_id: int, user_id: int, *, title: str, body: str
    ) -> LetterTemplate:
        if await self.profiles.get_by_id_for_user(profile_id, user_id) is None:
            raise ProfileNotAccessibleError("profile not found")
        return await self.templates.create(
            profile_id=profile_id, title=title, body=body
        )

    async def update(
        self,
        template_id: int,
        user_id: int,
        *,
        title: str | None,
        body: str | None,
    ) -> LetterTemplate:
        if await self.templates.get_for_user(template_id, user_id) is None:
            raise TemplateNotFoundError("template not found")
        return await self.templates.update(template_id, title=title, body=body)

    async def delete(self, template_id: int, user_id: int) -> None:
        if await self.templates.get_for_user(template_id, user_id) is None:
            raise TemplateNotFoundError("template not found")
        await self.templates.delete(template_id)
