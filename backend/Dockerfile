# Dockerfile для backend. Используется на Railway / в проде.
# Один образ для Web (uvicorn) и Worker (aiogram bot) — разные CMD задаются
# в Railway service settings.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1

# uv из официального slim-образа (та же версия что в CI)
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/

WORKDIR /app

# Пакеты:
# - curl, ca-certificates — healthcheck + миграции
# - chromium — headless-браузер для парсера hh.ru (--dump-dom, обход антибота).
#   Системный Chromium на Debian ставится в /usr/bin/chromium и тянет нужные libs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates chromium \
    && rm -rf /var/lib/apt/lists/*

# Путь к Chromium для парсера (src/sources/hh_chrome.py читает CHROME_BINARY).
ENV CHROME_BINARY=/usr/bin/chromium

# 1) Сначала манифесты — кэшируем слой с зависимостями
COPY pyproject.toml uv.lock .python-version ./

# 2) Ставим зависимости (без dev и без самого проекта — пакет монтируется ниже)
RUN uv sync --frozen --no-install-project --no-dev

# 3) Исходники
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

# PATH для venv-бинарей
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Простой healthcheck (Railway также делает свой по HTTP)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Дефолтная команда — Web. Worker (бот) переопределит CMD в Railway service.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
