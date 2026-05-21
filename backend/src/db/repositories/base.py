"""Базовое репозитория-родитель.

В v0.1 умышленно тонкий — только то, что нужно реально. Расширяем по
требованию (не добавляем спекулятивные методы).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Хранит ссылку на async-сессию, открытую FastAPI dependency."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
