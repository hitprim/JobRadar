"""User-service: upsert юзера при авторизации через Telegram.

Создаёт юзера при первом логине, генерирует DEK + wrap'ит.
При повторном логине обновляет ник/имя и `last_active_at`.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.db.repositories.user import UserRepository
from src.domain.user import User
from src.security.encryption import generate_dek, wrap_dek
from src.security.telegram_auth import TelegramUser


@dataclass(frozen=True)
class UpsertResult:
    user: User
    created: bool


class UserService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def upsert_from_telegram(self, tg_user: TelegramUser) -> UpsertResult:
        """Идемпотентный upsert по telegram_id."""
        existing = await self.users.get_by_telegram_id(tg_user.id)
        if existing is not None:
            await self.users.update_profile_fields(
                existing.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )
            await self.users.touch_last_active(existing.id)
            # Перечитываем, чтобы вернуть актуальные поля
            refreshed = await self.users.get_by_id(existing.id)
            assert refreshed is not None
            return UpsertResult(user=refreshed, created=False)

        # Новый юзер — генерируем DEK и шифруем его KEK'ом
        dek = generate_dek()
        wrapped = wrap_dek(dek)
        del dek  # plaintext DEK не нужен после wrap'а
        created = await self.users.create(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            dek_encrypted=wrapped,
        )
        await self.users.touch_last_active(created.id)
        refreshed = await self.users.get_by_id(created.id)
        assert refreshed is not None
        return UpsertResult(user=refreshed, created=True)
