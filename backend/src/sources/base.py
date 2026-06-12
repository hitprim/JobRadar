"""Базовый интерфейс источника вакансий.

Все источники (hh, habr, avito, ...) реализуют один метод `fetch`, который
по профилю и дополнительным параметрам возвращает список `ParsedVacancy`.

Маппинг профиля в специфичные параметры источника — внутри конкретной
реализации, чтобы Source-абстракция не протекала.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.domain.profile import Profile
from src.domain.vacancy import ParsedVacancy


class SourceError(Exception):
    """Базовое исключение источников."""


class SourceRateLimitedError(SourceError):
    """Источник вернул 429 / rate-limit. Парсер должен отложить следующий запуск."""


class Source(ABC):
    """Контракт источника вакансий."""

    source_type: str

    @abstractmethod
    async def fetch(
        self, profile: Profile, search_params: dict[str, Any] | None = None
    ) -> list[ParsedVacancy]:
        """Получает вакансии под профиль.

        Raises:
            SourceRateLimitedError: при 429.
            SourceError: для остальных ошибок (сеть, парсинг).
        """

    async def fetch_details(self, external_id: str) -> dict[str, Any] | None:
        """Опциональная on-demand подгрузка деталей вакансии (description,
        key_skills) в форме {"description": str|None, "key_skills": [{"name": str}]}.

        По умолчанию не реализовано (возвращает None). Источники, умеющие
        тянуть детали, переопределяют метод.
        """
        return None
