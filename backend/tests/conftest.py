"""Pytest fixtures.

Подключаемые позже:
- async_session — async-сессия БД на каждый тест (когда появятся repository-тесты)
- test_app — TestClient вокруг FastAPI (когда появятся API-тесты)
"""

from __future__ import annotations
