"""Profile-service: CRUD профилей.

Бизнес-правила:
- До MAX_ACTIVE_PROFILES активных профилей на юзера (POST → 409 при превышении).
- Новый профиль сразу делаем активным (users.active_profile_id).
- При soft-delete активного → active_profile_id = NULL.
"""

from __future__ import annotations

from src.db.repositories.profile import ProfileRepository
from src.db.repositories.user import UserRepository
from src.domain.profile import Profile, ProfileCreate, ProfileUpdate


class ProfileServiceError(Exception):
    """Базовое исключение профиль-сервиса (мапится на HTTP в роутере)."""


class ProfileLimitReachedError(ProfileServiceError):
    """Достигнут потолок активных профилей на юзера (MAX_ACTIVE_PROFILES)."""


class ProfileNotFoundError(ProfileServiceError):
    """Профиль не найден или принадлежит другому юзеру."""


class UserNotFoundError(ProfileServiceError):
    """Юзер не найден (теоретически не должно случаться при валидном JWT)."""


class ResumeTooLongError(ProfileServiceError):
    """Резюме превышает лимит длины."""


# Максимальная длина plaintext резюме до шифрования. ~100KB должно хватить
# с большим запасом (типовое CV в UTF-8 — 5-20KB).
MAX_RESUME_LENGTH = 100_000

# Потолок активных профилей на юзера. Защита от абуза/раздувания;
# для реальных сценариев (Backend + AI Engineer + ...) 5 более чем достаточно.
MAX_ACTIVE_PROFILES = 5


class ProfileService:
    def __init__(self, profiles: ProfileRepository, users: UserRepository) -> None:
        self.profiles = profiles
        self.users = users

    async def list_for_user(self, user_id: int) -> list[Profile]:
        return await self.profiles.list_active_for_user(user_id)

    async def create_for_user(self, user_id: int, data: ProfileCreate) -> Profile:
        existing_count = await self.profiles.count_active_for_user(user_id)
        if existing_count >= MAX_ACTIVE_PROFILES:
            raise ProfileLimitReachedError(
                f"Maximum {MAX_ACTIVE_PROFILES} active profiles allowed"
            )

        profile = await self.profiles.create(user_id, data)
        # Новый профиль сразу делаем активным — юзер хочет начать им пользоваться.
        await self.users.set_active_profile(user_id, profile.id)
        return profile

    async def update_for_user(self, profile_id: int, user_id: int, data: ProfileUpdate) -> Profile:
        updated = await self.profiles.update(profile_id, user_id, data)
        if updated is None:
            raise ProfileNotFoundError(f"profile {profile_id} not found")
        return updated

    async def soft_delete_for_user(self, profile_id: int, user_id: int) -> None:
        success = await self.profiles.soft_delete(profile_id, user_id)
        if not success:
            raise ProfileNotFoundError(f"profile {profile_id} not found")
        # Если удалили активный — сбрасываем active_profile_id
        user = await self.users.get_by_id(user_id)
        if user and user.active_profile_id == profile_id:
            await self.users.set_active_profile(user_id, None)

    async def activate_for_user(self, profile_id: int, user_id: int) -> None:
        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None or not profile.is_active:
            raise ProfileNotFoundError(f"active profile {profile_id} not found")
        await self.users.set_active_profile(user_id, profile_id)

    async def set_resume(self, profile_id: int, user_id: int, resume_text: str) -> None:
        if len(resume_text) > MAX_RESUME_LENGTH:
            raise ResumeTooLongError(f"resume exceeds {MAX_RESUME_LENGTH} characters")
        wrapped_dek = await self.users.get_dek_wrapped(user_id)
        if wrapped_dek is None:
            raise UserNotFoundError(f"user {user_id} not found")
        success = await self.profiles.set_resume(
            profile_id, user_id, wrapped_dek=wrapped_dek, resume_text=resume_text
        )
        if not success:
            raise ProfileNotFoundError(f"profile {profile_id} not found")

    async def get_resume(self, profile_id: int, user_id: int) -> str | None:
        wrapped_dek = await self.users.get_dek_wrapped(user_id)
        if wrapped_dek is None:
            raise UserNotFoundError(f"user {user_id} not found")
        # Проверяем что профиль наш (даже если резюме нет)
        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None:
            raise ProfileNotFoundError(f"profile {profile_id} not found")
        return await self.profiles.get_resume(profile_id, user_id, wrapped_dek=wrapped_dek)
