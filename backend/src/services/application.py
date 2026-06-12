"""ApplicationService: оркестрация трекера откликов.

Бизнес-правила v0.1:
- Дубликат (profile_id, vacancy_id) → DuplicateApplicationError → 409 в API
- Любые переходы статусов разрешены (включая откаты)
- history пишется при POST (запись 'sent') и при PATCH, если status изменился
- Reminders (next_reminder_at) только хранятся, рассылка в Day 22-23
"""

from __future__ import annotations

from src.db.repositories.application import (
    ApplicationRepository,
    DuplicateApplicationError,
)
from src.db.repositories.profile import ProfileRepository
from src.domain.application import (
    Application,
    ApplicationCreate,
    ApplicationExportRow,
    ApplicationListItem,
    ApplicationStatusHistory,
    ApplicationUpdate,
    FunnelStats,
)


class ApplicationServiceError(Exception):
    """Базовое исключение."""


class ProfileNotAccessibleError(ApplicationServiceError):
    """Профиль не найден или принадлежит другому юзеру."""


class VacancyNotFoundError(ApplicationServiceError):
    """Вакансии нет в БД."""


class ApplicationNotFoundError(ApplicationServiceError):
    """Application не найден или принадлежит другому юзеру."""


class ApplicationService:
    def __init__(
        self,
        applications: ApplicationRepository,
        profiles: ProfileRepository,
    ) -> None:
        self.applications = applications
        self.profiles = profiles

    async def list_for_user_profile(
        self,
        profile_id: int,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApplicationListItem]:
        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None:
            raise ProfileNotAccessibleError(f"profile {profile_id} not found")
        return await self.applications.list_for_profile_enriched(
            profile_id, limit=limit, offset=offset
        )

    async def create_for_user(
        self, profile_id: int, user_id: int, data: ApplicationCreate
    ) -> Application:
        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None:
            raise ProfileNotAccessibleError(f"profile {profile_id} not found")
        if not await self.applications.vacancy_exists(data.vacancy_id):
            raise VacancyNotFoundError(f"vacancy {data.vacancy_id} not found")

        # Repository поднимет DuplicateApplicationError при дубликате.
        # Не ловим — пробрасываем в endpoint, который сделает 409.
        return await self.applications.create(profile_id, data)

    async def update_for_user(
        self, application_id: int, user_id: int, data: ApplicationUpdate
    ) -> Application:
        app, status_changed = await self.applications.update_for_user(application_id, user_id, data)
        if app is None:
            raise ApplicationNotFoundError(f"application {application_id} not found")
        if status_changed:
            await self.applications.add_status_history(application_id, app.status)
        return app

    async def get_for_user(self, application_id: int, user_id: int) -> Application:
        app = await self.applications.get_by_id_for_user(application_id, user_id)
        if app is None:
            raise ApplicationNotFoundError(f"application {application_id} not found")
        return app

    async def list_history_for_user(
        self, application_id: int, user_id: int
    ) -> list[ApplicationStatusHistory]:
        # IDOR: проверяем что application наш
        app = await self.applications.get_by_id_for_user(application_id, user_id)
        if app is None:
            raise ApplicationNotFoundError(f"application {application_id} not found")
        return await self.applications.list_history(application_id)

    async def funnel_for_user_profile(self, profile_id: int, user_id: int) -> FunnelStats:
        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None:
            raise ProfileNotAccessibleError(f"profile {profile_id} not found")
        return await self.applications.funnel_for_profile(profile_id)

    async def export_for_user_profile(
        self, profile_id: int, user_id: int
    ) -> list[ApplicationExportRow]:
        profile = await self.profiles.get_by_id_for_user(profile_id, user_id)
        if profile is None:
            raise ProfileNotAccessibleError(f"profile {profile_id} not found")
        return await self.applications.list_for_export(profile_id)


# Re-export для удобства endpoint'а
__all__ = [
    "ApplicationNotFoundError",
    "ApplicationService",
    "ApplicationServiceError",
    "DuplicateApplicationError",
    "ProfileNotAccessibleError",
    "VacancyNotFoundError",
]
