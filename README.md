# JobRadar

Telegram MiniApp для соискателей в РФ. Парсинг hh.ru, LLM-скоринг вакансий, генерация сопроводительных, трекер откликов.

Полное описание продукта, архитектуры, модели данных и roadmap — в [`CLAUDE.md`](./CLAUDE.md).

## Быстрый старт (локально)

```bash
# 1. Конфигурация
cp .env.example .env
# Заполнить .env (см. комментарии в .env.example)

# 2. Поднять PostgreSQL
docker compose up -d

# 3. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload --port 8000

# Проверка:
# http://localhost:8000/health           → {"status": "ok"}
# http://localhost:8000/health/ready     → {"status": "ready", "db": "ok"}
# http://localhost:8000/docs             → Swagger UI
```

## Версия

v0.1 — Closed Beta (в разработке). См. roadmap в `CLAUDE.md`.
