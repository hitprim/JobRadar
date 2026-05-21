"""Абстракция LLM-провайдера и каталог промптов.

В v0.1 — DeepSeek через OpenRouter (`OpenRouterProvider`).
Заложена абстракция LLMProvider — провайдер меняется одной строкой
(например, на YandexGPT/GigaChat для 152-ФЗ при публичном запуске).

Структура prompts/:
    scoring/    — оценка вакансий, по файлу на категорию
    letters/    — генерация сопроводительных
    classification/ — авто-определение категории по резюме

Выбор промпта по profile.category. Если файла для категории нет — используется default.md.

DI: `get_llm_provider()` возвращает singleton-подобный OpenRouterProvider.
В тестах подменяется через FastAPI dependency_overrides на MockLLMProvider.
"""

from __future__ import annotations

from src.llm.base import (
    LLMError,
    LLMProvider,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from src.llm.openrouter import OpenRouterProvider


def get_llm_provider() -> LLMProvider:
    """Фабрика LLM-провайдера для FastAPI dependency.

    В v0.1 всегда возвращает OpenRouterProvider. Можно переопределить через
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider(...).
    """
    return OpenRouterProvider()


__all__ = [
    "LLMError",
    "LLMProvider",
    "LLMResponseValidationError",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "OpenRouterProvider",
    "get_llm_provider",
]
