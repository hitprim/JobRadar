"""OpenRouter-провайдер для DeepSeek (и совместимых).

Использует OpenAI-совместимый chat-completions endpoint OpenRouter:
    POST {base_url}/chat/completions
    Authorization: Bearer {api_key}

Request mode: `response_format={"type": "json_object"}` — модель обязана
вернуть валидный JSON.

Ретраи:
- llm_max_retries раз при 5xx / сетевых ошибках / невалидном JSON / схема не сошлась
- exponential backoff: 1s, 2s, 4s

ВАЖНО: не логируем содержимое user-prompt'а (там профиль с резюме!).
В логах только метаданные: model, status, tokens (если есть в response).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, TypeVar

import httpx
from loguru import logger
from pydantic import BaseModel, ValidationError

from src.config import settings
from src.llm.base import (
    LLMError,
    LLMProvider,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
)

T = TypeVar("T", bound=BaseModel)


def _schema_to_instruction(schema: type[BaseModel]) -> str:
    """Генерирует часть system-promt с JSON Schema."""
    s = schema.model_json_schema()
    return (
        "Respond with VALID JSON matching this JSON Schema. "
        "Do not include any text outside the JSON object.\n\n"
        f"```json\n{json.dumps(s, ensure_ascii=False, indent=2)}\n```"
    )


class OpenRouterProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = base_url or settings.openrouter_base_url
        self.model = model or settings.openrouter_model
        self.timeout = timeout or settings.openrouter_timeout_seconds
        self._client = client

    def _build_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # OpenRouter рекомендует заполнять для лучшего матчинга и метрик
                "HTTP-Referer": "https://github.com/hitprim/JobRadar",
                "X-Title": "JobRadar",
            },
            timeout=self.timeout,
        )

    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_schema: type[T],
    ) -> T:
        # Дополняем system promt инструкцией по JSON-схеме
        system_with_schema = f"{system}\n\n{_schema_to_instruction(response_schema)}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        client = self._build_client()
        owns_client = self._client is None
        max_retries = settings.llm_max_retries
        last_error: Exception | None = None

        try:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post("/chat/completions", json=payload)
                except httpx.TimeoutException as exc:
                    last_error = LLMTimeoutError(str(exc))
                except httpx.HTTPError as exc:
                    last_error = LLMUnavailableError(f"network: {exc}")
                else:
                    if response.status_code >= 500:
                        last_error = LLMUnavailableError(
                            f"openrouter {response.status_code}: {response.text[:200]}"
                        )
                    elif response.status_code >= 400:
                        # 4xx — не ретраим (наша ошибка в запросе)
                        raise LLMError(f"openrouter {response.status_code}: {response.text[:200]}")
                    else:
                        try:
                            parsed = self._parse_response(response.json(), response_schema)
                            logger.bind(
                                model=self.model,
                                attempt=attempt + 1,
                            ).info("llm: ok")
                            return parsed
                        except LLMResponseValidationError as exc:
                            last_error = exc
                            logger.bind(attempt=attempt + 1).warning(
                                "llm: response validation failed, retrying"
                            )

                # Backoff перед следующей попыткой
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)

            # Все попытки исчерпаны
            assert last_error is not None
            raise last_error
        finally:
            if owns_client:
                await client.aclose()

    def _parse_response(self, payload: dict[str, Any], schema: type[T]) -> T:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseValidationError(f"unexpected response shape: {exc}") from exc

        # content — это JSON-строка. Парсим в dict, валидируем схему.
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMResponseValidationError(f"response is not valid JSON: {exc}") from exc

        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise LLMResponseValidationError(
                f"response doesn't match schema: {exc.errors()[:3]}"
            ) from exc
