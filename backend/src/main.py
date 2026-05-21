"""FastAPI entrypoint.

Запуск (dev):
    uv run uvicorn src.main:app --reload --port 8000

Endpoints v0.1:
    GET /health        — liveness
    GET /health/ready  — readiness (проверка БД)

Бизнес-роутеры (/api/auth, /api/profiles, ...) подключаются по мере реализации.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import text

from src.config import settings
from src.db.session import engine
from src.logging_setup import setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.bind(env=settings.env).info("JobRadar API starting")
    try:
        yield
    finally:
        await engine.dispose()
        logger.info("JobRadar API stopped")


app = FastAPI(
    title="JobRadar API",
    version="0.1.0",
    description="Backend для JobRadar — Telegram MiniApp для поиска работы в РФ.",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness probe — всегда 200, если процесс жив."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def ready() -> JSONResponse:
    """Readiness probe — проверяет, что БД доступна."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.bind(error=str(exc)).error("readiness check failed: db unavailable")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "db": "fail"},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "db": "ok"},
    )
