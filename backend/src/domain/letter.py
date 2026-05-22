"""Domain-объект Letter (сопроводительное письмо)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Letter(BaseModel):
    """Сгенерированное сопроводительное."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    profile_id: int
    vacancy_id: int
    text: str | None
    prompt_used: str | None
    used_in_application: bool
    created_at: datetime
