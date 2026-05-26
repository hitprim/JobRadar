# JobRadar

Telegram MiniApp для соискателей в РФ. Парсинг hh.ru, LLM-скоринг вакансий, генерация сопроводительных, трекер откликов.

Полное описание продукта, архитектуры, модели данных и roadmap — в [`CLAUDE.md`](./CLAUDE.md).
Пошаговый деплой в прод — [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md).

## Быстрый старт (локально)

### 1. Конфигурация

```bash
cp .env.example .env
# Заполнить .env. Сгенерировать секреты:
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python -c "import os, base64; print('ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
```

### 2. Postgres

```bash
docker compose up -d
```

### 3. Backend (FastAPI)

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload --port 8000
# → http://localhost:8000/health, /health/ready, /docs (Swagger)
```

### 4. Telegram bot (отдельный процесс)

```bash
cd backend
uv run python -m src.bot.main
```

### 5. Frontend (React MiniApp)

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
# В обычном браузере без Telegram — автоматический dev-fallback на POST /api/auth/dev
```

## Архитектура

- **Backend:** Python 3.12 + FastAPI + SQLAlchemy 2.0 async + Postgres 16 + Alembic
- **LLM:** DeepSeek через OpenRouter (абстракция `LLMProvider`)
- **Парсинг:** hh.ru публичный API (OAuth отключён с 15.12.2025)
- **Шифрование резюме:** envelope encryption KEK + per-user DEK (AES-256-GCM)
- **Bot:** aiogram 3, long polling
- **Frontend:** React 18 + TS + Vite + Tailwind + React Router v7 + TanStack Query + Zustand
- **CI:** GitHub Actions — ruff + mypy + pytest + frontend tsc/eslint/build
- **Деплой v0.1:** Railway (backend + Postgres) + Cloudflare Pages (frontend)

## Версия

v0.1 — Closed Beta (готова). См. roadmap и принципы продукта в `CLAUDE.md`.
