"""Unit-тесты OpenRouterProvider через httpx.MockTransport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.llm.base import (
    LLMError,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from src.llm.openrouter import OpenRouterProvider
from src.llm.scoring import ScoringResult


def _mock_client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer test"},
    )


def _good_payload(**override: Any) -> dict:
    body = {
        "score": 80,
        "reason": "Стек совпадает по большей части. Зарплата в диапазоне.",
        "red_flags": [],
        "green_flags": ["clear salary", "remote ok"],
    }
    body.update(override)
    return {"choices": [{"message": {"role": "assistant", "content": json.dumps(body)}}]}


class TestComplete:
    async def test_ok(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith("/chat/completions")
            payload = json.loads(request.content)
            assert payload["model"]  # модель проставлена
            assert payload["response_format"]["type"] == "json_object"
            return httpx.Response(200, json=_good_payload())

        provider = OpenRouterProvider(client=_mock_client(handler))
        result = await provider.complete(system="sys", user="usr", response_schema=ScoringResult)
        assert isinstance(result, ScoringResult)
        assert result.score == 80

    async def test_retry_then_success(self) -> None:
        attempts = {"n": 0}

        def handler(_: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            if attempts["n"] == 1:
                # Первый ответ — невалидный JSON
                return httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": "not json"}}]},
                )
            return httpx.Response(200, json=_good_payload())

        provider = OpenRouterProvider(client=_mock_client(handler))
        result = await provider.complete(system="s", user="u", response_schema=ScoringResult)
        assert result.score == 80
        assert attempts["n"] == 2

    async def test_validation_failure_after_all_retries(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

        provider = OpenRouterProvider(client=_mock_client(handler))
        with pytest.raises(LLMResponseValidationError):
            await provider.complete(system="s", user="u", response_schema=ScoringResult)

    async def test_500_retried_then_raised(self) -> None:
        n = {"n": 0}

        def handler(_: httpx.Request) -> httpx.Response:
            n["n"] += 1
            return httpx.Response(500, text="server down")

        provider = OpenRouterProvider(client=_mock_client(handler))
        with pytest.raises(LLMUnavailableError):
            await provider.complete(system="s", user="u", response_schema=ScoringResult)
        # max_retries=2 → 3 попытки
        assert n["n"] == 3

    async def test_400_not_retried(self) -> None:
        n = {"n": 0}

        def handler(_: httpx.Request) -> httpx.Response:
            n["n"] += 1
            return httpx.Response(400, text="bad request")

        provider = OpenRouterProvider(client=_mock_client(handler))
        with pytest.raises(LLMError):
            await provider.complete(system="s", user="u", response_schema=ScoringResult)
        assert n["n"] == 1

    async def test_timeout_retried(self) -> None:
        n = {"n": 0}

        def handler(_: httpx.Request) -> httpx.Response:
            n["n"] += 1
            raise httpx.ConnectTimeout("timed out")

        provider = OpenRouterProvider(client=_mock_client(handler))
        with pytest.raises(LLMTimeoutError):
            await provider.complete(system="s", user="u", response_schema=ScoringResult)
        assert n["n"] == 3

    async def test_score_below_zero_in_response_rejected(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_good_payload(score=-5),
            )

        provider = OpenRouterProvider(client=_mock_client(handler))
        with pytest.raises(LLMResponseValidationError):
            await provider.complete(system="s", user="u", response_schema=ScoringResult)
