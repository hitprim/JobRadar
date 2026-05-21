"""Async-сессии SQLAlchemy.

Использование в FastAPI:

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.db.session import get_session

    @router.get("/profiles")
    async def list_profiles(session: AsyncSession = Depends(get_session)):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionMaker = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency для получения сессии БД с авто-rollback при исключении."""
    async with SessionMaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
