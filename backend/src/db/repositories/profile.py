"""Repository для profiles.

Резюме (resume_encrypted) хранится в БД как зашифрованный blob.
Чтение/запись резюме — отдельными методами (get_resume / set_resume),
которые требуют wrapped_dek юзера. Это не позволяет случайно вернуть
шифротекст в обычном запросе профиля.
"""

from __future__ import annotations

from sqlalchemy import func, select, update

from src.db.models import Profile as ProfileORM
from src.db.repositories.base import BaseRepository
from src.domain.profile import Profile, ProfileCreate, ProfileUpdate
from src.security.encryption import decrypt_resume, encrypt_resume


def _to_domain(orm: ProfileORM) -> Profile:
    """Маппинг ORM → Domain. has_resume вычисляется из наличия шифротекста."""
    return Profile(
        id=orm.id,
        user_id=orm.user_id,
        name=orm.name,
        category=orm.category,  # type: ignore[arg-type]
        stack=list(orm.stack or []),
        grade=orm.grade,  # type: ignore[arg-type]
        salary_from=orm.salary_from,
        salary_to=orm.salary_to,
        salary_currency=orm.salary_currency,
        work_format=list(orm.work_format or []),  # type: ignore[arg-type]
        schedule=list(orm.schedule or []),  # type: ignore[arg-type]
        area_ids=list(orm.area_ids or []),
        exclude_keywords=list(orm.exclude_keywords or []),
        has_resume=orm.resume_encrypted is not None,
        category_data=orm.category_data,
        is_active=orm.is_active,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


class ProfileRepository(BaseRepository):
    async def get_by_id(self, profile_id: int) -> Profile | None:
        orm = await self.session.get(ProfileORM, profile_id)
        return _to_domain(orm) if orm else None

    async def get_by_id_for_user(self, profile_id: int, user_id: int) -> Profile | None:
        """Возвращает профиль только если он принадлежит юзеру.

        Защита от IDOR — даже если кто-то знает чужой profile_id, он его
        не увидит.
        """
        orm = await self.session.get(ProfileORM, profile_id)
        if orm is None or orm.user_id != user_id:
            return None
        return _to_domain(orm)

    async def list_active_for_user(self, user_id: int) -> list[Profile]:
        stmt = (
            select(ProfileORM)
            .where(ProfileORM.user_id == user_id, ProfileORM.is_active.is_(True))
            .order_by(ProfileORM.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return [_to_domain(orm) for orm in result.scalars().all()]

    async def count_active_for_user(self, user_id: int) -> int:
        stmt = select(func.count(ProfileORM.id)).where(
            ProfileORM.user_id == user_id, ProfileORM.is_active.is_(True)
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def create(self, user_id: int, data: ProfileCreate) -> Profile:
        orm = ProfileORM(
            user_id=user_id,
            name=data.name,
            category=data.category,
            stack=data.stack or None,
            grade=data.grade,
            salary_from=data.salary_from,
            salary_to=data.salary_to,
            salary_currency=data.salary_currency,
            work_format=data.work_format or None,
            schedule=data.schedule or None,
            area_ids=data.area_ids or None,
            exclude_keywords=data.exclude_keywords or None,
            category_data=data.category_data,
            is_active=True,
        )
        self.session.add(orm)
        await self.session.flush()
        return _to_domain(orm)

    async def update(self, profile_id: int, user_id: int, data: ProfileUpdate) -> Profile | None:
        """Атомарный UPDATE ... RETURNING. Возвращает None если профиль чужой/не найден."""
        patch = data.model_dump(exclude_unset=True)
        if not patch:
            # PATCH без полей — просто отдаём текущее состояние
            return await self.get_by_id_for_user(profile_id, user_id)
        stmt = (
            update(ProfileORM)
            .where(ProfileORM.id == profile_id, ProfileORM.user_id == user_id)
            .values(**patch)
            .returning(ProfileORM)
            .execution_options(synchronize_session="fetch")
        )
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return _to_domain(orm) if orm else None

    async def soft_delete(self, profile_id: int, user_id: int) -> bool:
        """Возвращает True если что-то изменилось."""
        orm = await self.session.get(ProfileORM, profile_id)
        if orm is None or orm.user_id != user_id or not orm.is_active:
            return False
        orm.is_active = False
        return True

    async def set_resume(
        self, profile_id: int, user_id: int, *, wrapped_dek: bytes, resume_text: str
    ) -> bool:
        """Шифрует резюме DEK'ом юзера и сохраняет. True при успехе."""
        orm = await self.session.get(ProfileORM, profile_id)
        if orm is None or orm.user_id != user_id:
            return False
        orm.resume_encrypted = encrypt_resume(wrapped_dek, resume_text)
        return True

    async def get_resume(self, profile_id: int, user_id: int, *, wrapped_dek: bytes) -> str | None:
        """Расшифровывает резюме. None если профиль не наш или резюме нет."""
        orm = await self.session.get(ProfileORM, profile_id)
        if orm is None or orm.user_id != user_id or orm.resume_encrypted is None:
            return None
        return decrypt_resume(wrapped_dek, orm.resume_encrypted)

    async def get_resume_encrypted(self, profile_id: int, user_id: int) -> bytes | None:
        """Возвращает сырое шифр-blob без расшифровки. Дешифровка — на стороне сервиса."""
        orm = await self.session.get(ProfileORM, profile_id)
        if orm is None or orm.user_id != user_id:
            return None
        return orm.resume_encrypted
