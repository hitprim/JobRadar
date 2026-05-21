"""Domain-объекты для вакансий и связанного.

Vacancy — то, что хранится в БД.
ParsedVacancy — то, что возвращает Source (промежуточный контракт между
парсером и сервисом-сохранятором). Поля те же, но без id (его выдаст БД).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class Vacancy(BaseModel):
    """Вакансия из БД."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

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


class ParsedVacancy(BaseModel):
    """Что возвращает Source.fetch — нормализованная вакансия до записи в БД."""

    external_id: str
    source_type: str
    title: str | None = None
    company_name: str | None = None
    company_id: str | None = None
    salary_from: int | None = None
    salary_to: int | None = None
    salary_currency: str | None = None
    url: str | None = None
    area_name: str | None = None
    schedule: str | None = None
    experience: str | None = None
    description: str | None = None
    key_skills: list[str] = []
    published_at: datetime | None = None
    raw_data: dict[str, Any] | None = None


class VacancyReaction(BaseModel):
    """Реакция юзера на вакансию (свайп)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: int
    profile_id: int
    vacancy_id: int
    reaction: str | None  # "like" | "skip" | "save" | None
    score: int | None
    score_reason: str | None
    red_flags: list[str]
    scored_at: datetime | None


class FeedItem(BaseModel):
    """Элемент ленты — вакансия + реакция (если есть)."""

    vacancy: Vacancy
    reaction: VacancyReaction | None
