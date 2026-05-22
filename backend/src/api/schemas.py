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


# ============================================================================
# Sources
# ============================================================================


class SourcePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    type: str
    search_params: dict[str, Any] | None
    is_active: bool
    last_parsed_at: datetime | None
    last_status: str | None
    last_error: str | None
    vacancies_today: int


class SourceCreateRequest(BaseModel):
    type: str = Field(default="hh", pattern="^(hh|habr|avito|custom)$")
    search_params: dict[str, Any] | None = None


class ParseResultPublic(BaseModel):
    source_id: int
    fetched: int
    inserted: int
    updated: int
    status: str
    error: str | None = None


# ============================================================================
# Vacancies + Feed
# ============================================================================


class VacancyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    source_type: str
    title: str | None
    company_name: str | None
    company_id: str | None
    salary_from: int | None
    salary_to: int | None
    salary_currency: str | None
    url: str | None
    area_name: str | None
    schedule: str | None
    experience: str | None
    description: str | None
    key_skills: list[str]
    published_at: datetime | None
    parsed_at: datetime


class VacancyReactionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reaction: str | None
    score: int | None
    score_reason: str | None
    red_flags: list[str]
    scored_at: datetime | None


class FeedItemPublic(BaseModel):
    vacancy: VacancyPublic
    reaction: VacancyReactionPublic | None


class ReactionRequest(BaseModel):
    reaction: str = Field(pattern="^(like|skip|save)$")


# ============================================================================
# Scoring
# ============================================================================


class ScoreResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str
    red_flags: list[str] = Field(default_factory=list)
    green_flags: list[str] = Field(default_factory=list)
    from_cache: bool


# ============================================================================
# Letters
# ============================================================================


class LetterPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    vacancy_id: int
    text: str | None
    prompt_used: str | None
    used_in_application: bool
    created_at: datetime


class LetterGenerateRequest(BaseModel):
    extra_instructions: str | None = Field(default=None, max_length=2000)


class LetterGenerateResponse(BaseModel):
    letter: LetterPublic
    draft_notes: list[str] = Field(default_factory=list)


class LetterPatchRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=5000)
    used_in_application: bool | None = None


# Resolve forward ref
TelegramAuthResponse.model_rebuild()
