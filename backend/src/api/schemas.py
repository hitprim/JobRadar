"""Pydantic-схемы (DTO) для HTTP API.

Это внешний контракт. Может отличаться от domain-моделей в полях/именах.
Сейчас почти 1-в-1, но разделение позволяет менять API без правки domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.profile import (
    Experience,
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
    experience: list[Experience]
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
    experience: list[Experience] = Field(default_factory=list)
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
    experience: list[Experience] | None = None
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


class RefreshAcceptedPublic(BaseModel):
    """Ответ async-refresh: парсинг запущен в фоне, результат придёт пушем."""

    source_id: int
    status: str = "started"


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
    # True → описание ещё подгружается в фоне (Chrome), клиенту стоит опросить
    # эндпоинт повторно. False → описание актуально (есть либо его нет вовсе).
    description_pending: bool = False


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
    # Агрегат отзывов о компании (для бейджа respect-score). None — если у
    # компании ещё нет отзывов или её нельзя идентифицировать.
    company_review: CompanyReviewSummaryPublic | None = None


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


# ============================================================================
# Letter templates (сохранённые шаблоны)
# ============================================================================


class LetterTemplatePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    title: str
    body: str
    created_at: datetime
    updated_at: datetime


class LetterTemplateCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=5000)


class LetterTemplatePatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, min_length=1, max_length=5000)


# ============================================================================
# Applications (Tracker)
# ============================================================================


class ApplicationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    vacancy_id: int
    status: str
    cover_letter: str | None
    notes: str | None
    next_reminder_at: datetime | None
    reminder_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationListItemPublic(BaseModel):
    """Элемент списка трекера: application + заголовок/компания/ссылка вакансии."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    vacancy_id: int
    status: str
    cover_letter: str | None
    notes: str | None
    next_reminder_at: datetime | None
    reminder_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
    vacancy_title: str | None
    company_name: str | None
    vacancy_url: str | None


class ApplicationCreateRequest(BaseModel):
    vacancy_id: int
    cover_letter: str | None = Field(default=None, max_length=10_000)
    notes: str | None = Field(default=None, max_length=5_000)
    next_reminder_at: datetime | None = None


_STATUS_PATTERN = r"^(sent|hr|tech|final|offer|reject)$"


class ApplicationPatchRequest(BaseModel):
    status: str | None = Field(default=None, pattern=_STATUS_PATTERN)
    cover_letter: str | None = Field(default=None, max_length=10_000)
    notes: str | None = Field(default=None, max_length=5_000)
    next_reminder_at: datetime | None = None


class ApplicationStatusHistoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: str
    changed_at: datetime


class FunnelPublic(BaseModel):
    total: int
    counts: dict[str, int]
    conversion_rates: dict[str, float]


# ============================================================================
# Company reviews (отзывы о компаниях об отношении к соискателям)
# ============================================================================

_RESPONDED_PATTERN = r"^(fast|slow|ignored)$"
_RESPECT_PATTERN = r"^(respectful|neutral|dismissive)$"
_FEEDBACK_PATTERN = r"^(detailed|formal|none)$"
_HONESTY_PATTERN = r"^(matched|minor|mismatch)$"
_PROCESS_PATTERN = r"^(smooth|tolerable|draining)$"


class CompanyReviewCreateRequest(BaseModel):
    responded: str = Field(pattern=_RESPONDED_PATTERN)
    respect: str = Field(pattern=_RESPECT_PATTERN)
    feedback: str = Field(pattern=_FEEDBACK_PATTERN)
    honesty: str = Field(pattern=_HONESTY_PATTERN)
    process: str = Field(pattern=_PROCESS_PATTERN)
    text: str | None = Field(default=None, max_length=2000)


class CompanyReviewPublic(BaseModel):
    """Один отзыв. Без user_id — отзывы анонимны для читателей."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    responded: str
    respect: str
    feedback: str
    honesty: str
    process: str
    text: str | None
    score: int
    created_at: datetime


class CompanyReviewSummaryPublic(BaseModel):
    """Краткий агрегат для бейджа (в ленте/на карточке)."""

    respect_score: int | None
    review_count: int


class CompanyReviewReportResponse(BaseModel):
    """Результат жалобы на отзыв."""

    report_count: int
    hidden: bool


class CompanyReviewViewPublic(BaseModel):
    """Полный взгляд на отзывы компании для экрана вакансии."""

    company_key: str | None
    company_name: str | None
    respect_score: int | None
    review_count: int
    can_review: bool
    my_review: CompanyReviewPublic | None
    reviews: list[CompanyReviewPublic]


# Resolve forward refs
TelegramAuthResponse.model_rebuild()
FeedItemPublic.model_rebuild()
