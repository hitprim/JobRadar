"""Repository для users."""

from __future__ import annotations

from sqlalchemy import select

from src.db.models import User as UserORM
from src.db.repositories.base import BaseRepository
from src.domain.user import User


class UserRepository(BaseRepository):
    async def get_by_id(self, user_id: int) -> User | None:
        stmt = select(UserORM).where(UserORM.id == user_id)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return User.model_validate(orm) if orm else None

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(UserORM).where(UserORM.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return User.model_validate(orm) if orm else None

    async def get_dek_wrapped(self, user_id: int) -> bytes | None:
        """Возвращает завёрнутый DEK (читать только когда нужно для резюме)."""
        stmt = select(UserORM.dek_encrypted).where(UserORM.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        dek_encrypted: bytes,
    ) -> User:
        orm = UserORM(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            dek_encrypted=dek_encrypted,
        )
        self.session.add(orm)
        await self.session.flush()  # получаем id без commit'а
        return User.model_validate(orm)

    async def update_profile_fields(
        self,
        user_id: int,
        *,
        username: str | None,
        first_name: str | None,
    ) -> None:
        """Обновляет ник и имя из свежего initData (после каждого login'а)."""
        orm = await self.session.get(UserORM, user_id)
        if orm is None:
            return
        orm.username = username
        orm.first_name = first_name

    async def touch_last_active(self, user_id: int) -> None:
        """Помечает время последней активности."""
        from datetime import UTC, datetime

        orm = await self.session.get(UserORM, user_id)
        if orm is None:
            return
        orm.last_active_at = datetime.now(UTC)

    async def set_active_profile(self, user_id: int, profile_id: int | None) -> None:
        orm = await self.session.get(UserORM, user_id)
        if orm is None:
            return
        orm.active_profile_id = profile_id
