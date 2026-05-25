"""Domain-объекты для трекера откликов."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Возможные статусы. В v0.1 переходы не валидируем — юзер свободен.
ApplicationStatus = Literal["sent", "hr", "tech", "final", "offer", "reject"]
APPLICATION_STATUSES: tuple[ApplicationStatus, ...] = (
    "sent",
    "hr",
    "tech",
    "final",
    "offer",
    "reject",
)


class Application(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    profile_id: int
    vacancy_id: int
    status: ApplicationStatus
    cover_letter: str | None
    notes: str | None
    next_reminder_at: datetime | None
    reminder_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationStatusHistory(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    application_id: int
    status: ApplicationStatus
    changed_at: datetime


class ApplicationCreate(BaseModel):
    """Внутренний контракт создания."""

    vacancy_id: int
    cover_letter: str | None = Field(default=None, max_length=10_000)
    notes: str | None = Field(default=None, max_length=5_000)
    next_reminder_at: datetime | None = None


class ApplicationUpdate(BaseModel):
    """PATCH: все поля опциональны. status триггерит запись в history."""

    status: ApplicationStatus | None = None
    cover_letter: str | None = Field(default=None, max_length=10_000)
    notes: str | None = Field(default=None, max_length=5_000)
    next_reminder_at: datetime | None = None


class FunnelStats(BaseModel):
    """Воронка откликов: counts по current status + conversion rates."""

    total: int
    counts: dict[str, int]  # status → count, все 6 статусов всегда (нули включены)
    conversion_rates: dict[str, float]  # status → % от sent (0.0..1.0)
