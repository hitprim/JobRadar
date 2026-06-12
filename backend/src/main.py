"""FastAPI entrypoint.

Запуск (dev):
    uv run uvicorn src.main:app --reload --port 8000

Endpoints v0.1:
    GET  /health                            — liveness
    GET  /health/ready                      — readiness (проверка БД)
    POST /api/auth/telegram                 — авторизация через Telegram initData
    GET  /api/profiles                      — список профилей юзера
    POST /api/profiles                      — создать профиль
    PATCH /api/profiles/{id}                — обновить (без resume)
    PUT  /api/profiles/{id}/resume          — обновить резюме
    GET  /api/profiles/{id}/resume          — получить резюме
    DELETE /api/profiles/{id}               — soft-delete
    POST /api/profiles/{id}/activate        — сделать активным
    GET  /api/profiles/{id}/sources         — список источников профиля
    POST /api/profiles/{id}/sources         — добавить источник
    DELETE /api/sources/{id}                — удалить источник
    POST /api/sources/{id}/refresh          — ручной запуск парсинга
    GET  /api/profiles/{id}/feed            — лента вакансий
    GET  /api/vacancies/{id}                — детали вакансии (с lazy fetch_details)
    POST /api/vacancies/{id}/reaction       — like/skip/save
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import text

from src.api import applications as applications_router
from src.api import auth as auth_router
from src.api import billing as billing_router
from src.api import company_reviews as company_reviews_router
from src.api import letter_templates as letter_templates_router
from src.api import letters as letters_router
from src.api import profiles as profiles_router
from src.api import sources as sources_router
from src.api import vacancies as vacancies_router
from src.config import settings
from src.db.session import engine
from src.logging_setup import setup_logging
from src.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.bind(env=settings.env).info("JobRadar API starting")
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        await engine.dispose()
        logger.info("JobRadar API stopped")


app = FastAPI(
    title="JobRadar API",
    version="0.1.0",
    description="Backend для JobRadar — Telegram MiniApp для поиска работы в РФ.",
    lifespan=lifespan,
)

# CORS — в dev '*', в prod whitelist из env (валидация в settings.cors_origins).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# Бизнес-роутеры. sources/vacancies подключаются без префикса — пути полные.
app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(profiles_router.router, prefix="/api/profiles", tags=["profiles"])
app.include_router(sources_router.router)
app.include_router(vacancies_router.router)
app.include_router(letters_router.router)
app.include_router(letter_templates_router.router)
app.include_router(applications_router.router)
app.include_router(company_reviews_router.router)
app.include_router(billing_router.router)


# --- Опциональная раздача собранного SPA (локальный ngrok-деплой) ---
# Если FRONTEND_DIST_PATH указывает на существующую папку — backend отдаёт
# фронт с того же origin, что и /api (удобно для одного ngrok-туннеля).
# В проде путь пустой → этот блок не активируется (фронт на Cloudflare/Netlify).
_dist = settings.frontend_dist_path.strip()
if _dist and os.path.isdir(_dist):
    _assets_dir = os.path.join(_dist, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    _index = os.path.join(_dist, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        """SPA-fallback: отдаём статфайл если есть, иначе index.html
        (клиентский роутинг React Router). API-роуты зарегистрированы выше и
        имеют приоритет.

        Синхронный хендлер — FastAPI выполнит его в threadpool, поэтому
        блокирующие os.path-проверки здесь безопасны (и не триггерят async-lint).
        """
        candidate = os.path.join(_dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_index)

    logger.bind(dist=_dist).info("SPA static serving enabled")
