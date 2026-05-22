"""Тестовые моки для LLM."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.llm.base import LLMProvider, LLMResponseValidationError

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    """Возвращает фиксированный ответ либо последовательность ответов.

    Подсчитывает вызовы → удобно проверять кэширование.
    """

    def __init__(
        self,
        response: dict | None = None,
        responses: list[dict] | None = None,
    ) -> None:
        if responses is None and response is None:
            raise ValueError("provide response or responses")
        self._queue: list[dict] = list(responses) if responses else [response]  # type: ignore[list-item]
        self.calls: list[tuple[str, str, type[BaseModel]]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_schema: type[T],
    ) -> T:
        self.calls.append((system, user, response_schema))
        if not self._queue:
            raise RuntimeError("MockLLMProvider: no more queued responses")
        data = self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
        try:
            return response_schema.model_validate(data)
        except ValidationError as exc:
            raise LLMResponseValidationError(
                f"mock response doesn't match schema: {exc.errors()[:3]}"
            ) from exc

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def last_user_message(self) -> str:
        assert self.calls, "no calls recorded"
        return self.calls[-1][1]

    def last_system_message(self) -> str:
        assert self.calls, "no calls recorded"
        return self.calls[-1][0]


def good_scoring_response(
    *,
    score: int = 82,
    reason: str = "Хороший матч по стеку и грейду. Зарплата в диапазоне.",
    red_flags: list[str] | None = None,
    green_flags: list[str] | None = None,
) -> dict:
    return {
        "score": score,
        "reason": reason,
        "red_flags": red_flags or [],
        "green_flags": green_flags or ["Чёткая ЗП", "Стек совпадает"],
    }


def good_letter_response(
    *,
    letter_text: str | None = None,
    draft_notes: list[str] | None = None,
) -> dict:
    if letter_text is None:
        # 250+ символов — попадает в min_length=200 schema
        letter_text = (
            "Здравствуйте! Меня заинтересовала ваша вакансия Senior Python "
            "разработчика в Acme. Особенно привлекла часть про микросервисы и "
            "Kubernetes — у меня есть опыт построения подобных систем на "
            "FastAPI и асинхронном Python. Готов обсудить детали на собеседовании."
        )
    return {
        "letter_text": letter_text,
        "draft_notes": draft_notes
        or ["used 'FastAPI' from profile", "mentioned 'Kubernetes' from vacancy"],
    }


def encode_as_openrouter_payload(data: dict) -> dict:
    """Оборачивает dict как ответ chat-completions для тестов OpenRouterProvider."""
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": json.dumps(data)},
                "finish_reason": "stop",
            }
        ],
        "model": "deepseek/deepseek-chat",
    }
