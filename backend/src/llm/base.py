"""Абстракция LLM-провайдера.

Реализации:
- OpenRouterProvider — основной, DeepSeek через OpenRouter
- MockLLMProvider — в тестах (см. tests/integration/mocks.py)

Контракт `complete(system, user, response_schema)`:
- system: системный промпт (роль, инструкции, схема ответа)
- user: пользовательский ввод (профиль + вакансия в `<user_input>` тегах)
- response_schema: pydantic-модель ожидаемого JSON-ответа
- возвращает экземпляр response_schema с валидированными полями
- ретраит до llm_max_retries раз при невалидном JSON / 5xx

В этом интерфейсе НЕТ потокового вывода, multi-turn разговоров и tool calls
— они не нужны в v0.1. Добавим в v0.2 при необходимости.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Базовое исключение LLM-провайдера."""


class LLMTimeoutError(LLMError):
    """Провайдер не уложился в timeout."""


class LLMUnavailableError(LLMError):
    """Провайдер недоступен / 5xx / сеть."""


class LLMResponseValidationError(LLMError):
    """LLM вернул JSON, не соответствующий схеме (после всех ретраев)."""


class LLMProvider(ABC):
    """Контракт LLM-провайдера. Реализации в src/llm/*.py."""

    @abstractmethod
    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_schema: type[T],
    ) -> T:
        """Получает structured-output из LLM.

        Raises:
            LLMTimeoutError: timeout.
            LLMUnavailableError: 5xx / сеть.
            LLMResponseValidationError: JSON не сошёлся со схемой даже после ретраев.
        """
