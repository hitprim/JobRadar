"""Domain-объект User.

Чистый pydantic. Используется внутри services как контракт между repository
и API. ORM-объекты не утекают за пределы repository.

Поле dek_encrypted умышленно НЕ включено — DEK расшифровывается только в
момент работы с резюме (через repository.get_user_dek), отдельно от обычных
запросов. Это уменьшает риск случайно залогировать ключ.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class User(BaseModel):
    """Юзер JobRadar (не путать с TelegramUser из security/telegram_auth)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    active_profile_id: int | None
    credits: int
    created_at: datetime
    last_active_at: datetime | None
