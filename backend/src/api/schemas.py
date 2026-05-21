"""Pydantic-схемы (DTO) для HTTP API.

Это внешний контракт. Может отличаться от domain-моделей в полях/именах.
Сейчас почти 1-в-1, но разделение позволяет менять API без правки domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.profile import (
    ProfileCategory,
    ProfileGrade,
    Schedule,
    WorkFormat,
)

# ============================================================================
# Auth
# ============================================================================


class TelegramAuthRequest(BaseModel):
    """Frontend отправляет initData как одну строку (Telegram.WebApp.initData)."""

    init_data: str = Field(min_length=1, max_length=8192)


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # секунды
    user: UserPublic
    is_new_user: bool


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    active_profile_id: int | None
    credits: int


# ============================================================================
# Profiles
# ============================================================================


class ProfilePublic(BaseModel):
    """Профиль для возврата клиенту. Без resume_encrypted — резюме отдельно."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    category: ProfileCategory
    stack: list[str]
    grade: ProfileGrade | None
    salary_from: int | None
    salary_to: int | None
    salary_currency: str
    work_format: list[WorkFormat]
    schedule: list[Schedule]
    area_ids: list[int]
    exclude_keywords: list[str]
    has_resume: bool
    category_data: dict[str, Any] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: ProfileCategory = "it"
    stack: list[str] = Field(default_factory=list, max_length=50)
    grade: ProfileGrade | None = None
    salary_from: int | None = Field(default=None, ge=0)
    salary_to: int | None = Field(default=None, ge=0)
    salary_currency: str = "RUR"
    work_format: list[WorkFormat] = Field(default_factory=list)
    schedule: list[Schedule] = Field(default_factory=list)
    area_ids: list[int] = Field(default_factory=list, max_length=50)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=50)
    category_data: dict[str, Any] | None = None


class ProfileUpdateRequest(BaseModel):
    """PATCH: все поля опциональны. Resume — отдельным endpoint'ом."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: ProfileCategory | None = None
    stack: list[str] | None = Field(default=None, max_length=50)
    grade: ProfileGrade | None = None
    salary_from: int | None = Field(default=None, ge=0)
    salary_to: int | None = Field(default=None, ge=0)
    salary_currency: str | None = None
    work_format: list[WorkFormat] | None = None
    schedule: list[Schedule] | None = None
    area_ids: list[int] | None = Field(default=None, max_length=50)
    exclude_keywords: list[str] | None = Field(default=None, max_length=50)
    category_data: dict[str, Any] | None = None


class ResumeUpdateRequest(BaseModel):
    resume_text: str = Field(min_length=1, max_length=100_000)


class ResumeResponse(BaseModel):
    resume_text: str | None  # None если резюме не было загружено


# Resolve forward ref
TelegramAuthResponse.model_rebuild()
