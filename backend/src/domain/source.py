"""Domain-объект Source (источник вакансий)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# В v0.1 поддерживаем только hh. Habr/Avito/custom — в v0.2+.
SourceType = Literal["hh", "habr", "avito", "custom"]


class Source(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    profile_id: int
    type: SourceType
    search_params: dict[str, Any] | None
    is_active: bool
    last_parsed_at: datetime | None
    last_status: str | None  # "ok" | "error" | "rate_limited"
    last_error: str | None
    vacancies_today: int


class SourceCreate(BaseModel):
    """Внутренний контракт создания источника."""

    type: SourceType = "hh"
    search_params: dict[str, Any] | None = Field(default=None)


class ParseResult(BaseModel):
    """Результат прогона парсера для одного источника."""

    source_id: int
    fetched: int  # сколько вакансий пришло из источника
    inserted: int  # сколько новых
    updated: int  # сколько обновили (existing external_id)
    status: Literal["ok", "error", "rate_limited"]
    error: str | None = None
