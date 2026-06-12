"""Domain-объект Profile.

`resume_encrypted` умышленно НЕ включён — резюме читается отдельным методом
repository.get_resume(profile_id, user_dek) → str, который расшифровывает на
лету. Так шифротекст не таскается по слоям без необходимости.

`has_resume` — bool-флаг показывает frontend'у, есть ли что показывать.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Категории профессий (см. CLAUDE.md → "Категории профессий v0.2")
ProfileCategory = Literal["it", "finance", "sales", "medical", "service", "production", "other"]
# Грейды. В v0.1 поддерживаем только IT-значения. Не-IT — в v0.2.
ProfileGrade = Literal["junior", "middle", "senior", "lead"]
WorkFormat = Literal["remote", "hybrid", "office"]
Schedule = Literal["fullDay", "shift", "flexible", "part"]
# Уровни опыта hh.ru — явный фильтр поиска (отдельно от grade, который для скоринга).
Experience = Literal["noExperience", "between1And3", "between3And6", "moreThan6"]


class Profile(BaseModel):
    """Профиль пользователя."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    user_id: int
    name: str
    category: ProfileCategory
    stack: list[str] = Field(default_factory=list)
    grade: ProfileGrade | None
    salary_from: int | None
    salary_to: int | None
    salary_currency: str
    work_format: list[WorkFormat] = Field(default_factory=list)
    schedule: list[Schedule] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    area_ids: list[int] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    has_resume: bool
    category_data: dict[str, Any] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProfileCreate(BaseModel):
    """Параметры создания профиля (внутренний контракт, не API-DTO)."""

    name: str = Field(min_length=1, max_length=100)
    category: ProfileCategory = "it"
    stack: list[str] = Field(default_factory=list)
    grade: ProfileGrade | None = None
    salary_from: int | None = Field(default=None, ge=0)
    salary_to: int | None = Field(default=None, ge=0)
    salary_currency: str = "RUR"
    work_format: list[WorkFormat] = Field(default_factory=list)
    schedule: list[Schedule] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    area_ids: list[int] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    category_data: dict[str, Any] | None = None


class ProfileUpdate(BaseModel):
    """Patch: все поля опциональны. Resume — отдельным endpoint'ом."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: ProfileCategory | None = None
    stack: list[str] | None = None
    grade: ProfileGrade | None = None
    salary_from: int | None = Field(default=None, ge=0)
    salary_to: int | None = Field(default=None, ge=0)
    salary_currency: str | None = None
    work_format: list[WorkFormat] | None = None
    schedule: list[Schedule] | None = None
    experience: list[Experience] | None = None
    area_ids: list[int] | None = None
    exclude_keywords: list[str] | None = None
    category_data: dict[str, Any] | None = None
