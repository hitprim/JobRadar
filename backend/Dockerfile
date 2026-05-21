# Dockerfile для backend. Используется на Railway / в проде.
# В dev запускаем локально через `uv run uvicorn ...`.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# uv ставим из официального slim-образа
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# Сначала только манифесты — кэшируем слой с зависимостями
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev || uv sync --no-dev

# Затем — исходники
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000

# Миграции запускаются отдельным шагом (Railway pre-deploy / `uv run alembic upgrade head`)
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
