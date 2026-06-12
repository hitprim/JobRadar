"""Fixtures для integration-тестов.

Стратегия:
- Подключаемся к настоящей PostgreSQL (та же DATABASE_URL из .env, в CI — service).
- Перед КАЖДЫМ тестом — `TRUNCATE users, profiles, vacancies, ... RESTART IDENTITY CASCADE`.
  Это даёт детерминированные id и независимость тестов.
- Override `get_session` через FastAPI dependency_overrides — отдаём собственную сессию.
- HTTP-клиент: httpx.AsyncClient через ASGITransport (без реального сетевого слоя).

Тесты предполагают что alembic уже накатил миграции (CI: отдельный шаг; локально: manual).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.db.session import get_session
from src.main import app

# Список таблиц, которые нужно очистить между тестами. Порядок не важен —
# TRUNCATE ... CASCADE сам разрулит FK. Не трогаем `config` (seed-данные нужны)
# и `alembic_version` (нужна для отслеживания миграций).
_TRUNCATE_TABLES = [
    "events",
    "application_status_history",
    "applications",
    "vacancy_reactions",
    "company_review_reports",
    "company_reviews",
    "letter_templates",
    "letters",
    "payments",
    "sources",
    "vacancies",
    "profiles",
    "users",
]


@pytest_asyncio.fixture(scope="session")
async def test_engine():  # noqa: ANN201 — pytest-asyncio fixture
    """Один engine на всю сессию pytest."""
    engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_clean(test_engine) -> AsyncIterator[None]:  # noqa: ANN001
    """Перед каждым тестом — truncate всех таблиц с пользовательскими данными."""
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def db_session(test_engine, db_clean) -> AsyncIterator[AsyncSession]:  # noqa: ANN001
    """Async-сессия, используется в тестах для подготовки данных."""
    Session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)  # noqa: N806
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine, db_clean) -> AsyncIterator[AsyncClient]:  # noqa: ANN001
    """HTTP-клиент, который пересоздаёт сессию для каждого запроса через override.

    Каждый запрос FastAPI открывает свой `async with Session()` (как в проде),
    поэтому коммиты в роутерах видны последующим запросам в том же тесте.
    """
    Session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)  # noqa: N806

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with Session() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = _override_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_session, None)
