# JobRadar

**Telegram MiniApp для соискателей в РФ.** Парсит вакансии с hh.ru, оценивает
совпадение с профилем через LLM, генерирует сопроводительные, ведёт трекер
откликов и собирает верифицированные отзывы об отношении компаний к кандидатам.

Это технический README: архитектура, подсистемы, API, конфигурация, локальный
запуск, тесты, деплой. Продуктовое видение, модель данных и roadmap — в
[`CLAUDE.md`](./CLAUDE.md). Пошаговый прод-деплой — в [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md).
Реестр техдолга — в [`docs/TECHDEBT.md`](./docs/TECHDEBT.md).

---

## Содержание

- [Стек](#стек)
- [Архитектура](#архитектура)
- [Backend: чистая архитектура](#backend-чистая-архитектура)
- [Подсистемы](#подсистемы)
- [HTTP API](#http-api)
- [Frontend](#frontend)
- [Модель данных и миграции](#модель-данных-и-миграции)
- [Конфигурация (.env)](#конфигурация-env)
- [Локальный запуск](#локальный-запуск)
- [Тесты](#тесты)
- [CI/CD и деплой](#cicd-и-деплой)
- [Безопасность](#безопасность)
- [Структура репозитория](#структура-репозитория)

---

## Стек

| Слой | Технологии |
|------|-----------|
| **Backend** | Python 3.12, FastAPI ≥0.115, Uvicorn, SQLAlchemy 2.0 (async) + asyncpg, Alembic, Pydantic v2 + pydantic-settings |
| **БД** | PostgreSQL 16 |
| **LLM** | DeepSeek через OpenRouter; абстракция `LLMProvider` (смена провайдера одной строкой) |
| **Парсинг** | headless Chrome (`--dump-dom`, без CDP) + `selectolax` (HTML-парсер); fallback — публичный API hh.ru |
| **Bot** | aiogram 3 (long polling) |
| **Шедулер** | APScheduler (in-process, опционально) |
| **Безопасность** | PyJWT (HS256), `cryptography` (AES-256-GCM envelope encryption), Telegram initData HMAC |
| **Логи** | loguru (text в dev, JSON в prod) |
| **Frontend** | React 18 + TypeScript 5.7, Vite 6, Tailwind 3, React Router 7, TanStack Query 5, Zustand 5, `@telegram-apps/sdk-react`, axios |
| **Тулинг** | uv (Python), ruff + mypy, pytest + pytest-asyncio; eslint + tsc |
| **CI/CD** | GitHub Actions; Railway (backend + Postgres + bot worker) + Cloudflare Pages (frontend) |

---

## Архитектура

```
┌──────────────────────────────────────────────┐
│        Telegram MiniApp (React SPA)          │
│  initData (HMAC) → JWT → Bearer на каждый     │
│  запрос. TanStack Query кэширует, Zustand —   │
│  auth-состояние.                              │
└───────────────────────┬──────────────────────┘
                        │ HTTPS / JSON
                        ▼
┌──────────────────────────────────────────────┐
│              FastAPI backend                  │
│  api/ (роутинг+DTO) → services/ (логика) →    │
│  db/repositories (SQL) → PostgreSQL           │
│  sources/ (парсер hh.ru) · llm/ (скоринг,     │
│  письма) · security/ (auth, шифрование)       │
│  + APScheduler (парсинг/алерты/напоминания)   │
└──────┬───────────────────────┬────────────────┘
       │                       │
       ▼                       ▼
┌─────────────┐        ┌──────────────────┐
│ PostgreSQL  │        │  OpenRouter API  │
│  (Alembic)  │        │   (DeepSeek)     │
└─────────────┘        └──────────────────┘
       ▲
       │ тот же код, отдельный процесс
┌──────┴───────────────────────────────────────┐
│        Telegram Bot (aiogram 3)              │
│  /start, уведомления, (оплата — стаб)         │
└──────────────────────────────────────────────┘
```

**Путь запроса (пример: лента вакансий):**
`GET /api/profiles/{id}/feed` → `CurrentUserId` (JWT-зависимость) → роутер в
`api/vacancies.py` → `FeedService` → репозитории `VacancyRepository` /
`ReactionRepository` / `CompanyReviewRepository` → маппинг ORM→domain→DTO → JSON.

**Backend как один origin (опционально):** если задан `FRONTEND_DIST_PATH`,
FastAPI сам раздаёт собранный SPA (`StaticFiles` + SPA-fallback на `index.html`),
так что и `/api`, и фронт доступны с одного origin — удобно для локального
ngrok-туннеля (см. `docker-compose.local.yml`). В проде путь пустой → фронт на
Cloudflare Pages, backend отдаёт только API.

---

## Backend: чистая архитектура

Строгое разделение слоёв (правила — в `CLAUDE.md`):

| Слой | Папка | Ответственность | Чего НЕ делает |
|------|-------|-----------------|----------------|
| **domain** | `src/domain/` | Чистые `pydantic`-модели (`frozen=True`, `from_attributes=True`) | Не знает про HTTP, SQL, LLM |
| **api** | `src/api/` | HTTP-роутинг, валидация, DTO (`schemas.py`), маппинг исключений сервиса → HTTP-коды | Без бизнес-логики и SQL |
| **services** | `src/services/` | Бизнес-логика, оркестрация репозиториев/LLM/источников, проверки доступа (IDOR через `profiles.user_id`) | Без прямого SQL |
| **db** | `src/db/` | SQLAlchemy 2.0: `models.py` (ORM), `repositories/` (вся работа с БД, возвращают domain-объекты) | Без бизнес-правил |
| **sources** | `src/sources/` | Парсеры источников по общему интерфейсу `Source` | — |
| **llm** | `src/llm/` | `LLMProvider` + промпты как файлы + структурированный парсинг | — |
| **security** | `src/security/` | Telegram-auth, JWT, шифрование, FastAPI-зависимости | — |

**Ключевой паттерн.** DTO (`api/schemas.py`) и domain (`domain/*.py`) разделены и
маппятся руками в сервисах — внешний контракт API можно менять, не трогая domain.
Репозитории наследуют `repositories/base.py` и **всегда** возвращают domain-модели,
а не ORM-объекты, изолируя SQLAlchemy от верхних слоёв.

---

## Подсистемы

### Аутентификация (`security/telegram_auth.py`, `jwt.py`, `deps.py`)
- Frontend передаёт `Telegram.WebApp.initData` → `POST /api/auth/telegram`.
- Backend валидирует HMAC-подпись секретом бота и проверяет свежесть `auth_date`
  (TTL `INIT_DATA_TTL_SECONDS`, защита от replay).
- При успехе — создаёт/находит юзера и выдаёт JWT (HS256, TTL 30 дней).
- `CurrentUserId` — FastAPI-зависимость, достаёт `user_id` из `Authorization: Bearer`.
- **Dev-fallback:** `POST /api/auth/dev` выдаёт токен без Telegram — фронт в обычном
  браузере использует его автоматически (упрощает локальную разработку).

### Шифрование резюме (`security/encryption.py`)
- **Envelope encryption.** Мастер-ключ KEK (`ENCRYPTION_KEY`, base64 от 32 байт)
  шифрует per-user DEK; DEK шифрует текст резюме (AES-256-GCM).
- В логи никогда не попадают текст резюме, имена, email — только `telegram_id` и
  счётчики операций.

### Парсер hh.ru (`sources/hh_chrome.py`, `sources/hh.py`, `services/parser.py`)
- Соискательский OAuth hh.ru отключён с 2025-12-15, а публичный API отдаёт 403 на
  серверных IP → основной путь — **headless Chrome** (`--headless --dump-dom`,
  без CDP), HTML парсится через `selectolax`.
- `PARSER_USE_CHROME` переключает `HhChromeSource` ↔ старый `HhSource` (API).
- Анти-бот меры: ограничение параллелизма (`PARSER_CONCURRENCY`), джиттер между
  страницами, экспоненциальный бэкофф, virtual-time-budget для рендера SPA,
  опциональный `--proxy-server`.
- **Lazy fetch описаний:** список выдачи парсится быстро; полное описание вакансии
  подгружается в фоне при открытии (`GET /api/vacancies/{id}` отдаёт
  `description_pending=true`, фронт опрашивает повторно).
- Все парсеры реализуют интерфейс `sources/base.py` — добавление Хабр/Авито (v0.2+)
  не трогает сервисы.

### Шедулер (`services/scheduler.py`, `notifications.py`)
- In-process APScheduler, по умолчанию **выключен** (`PARSER_ENABLED=false`);
  ручной парсинг через `POST /api/sources/{id}/refresh` работает всегда.
- Три джоба: парсинг источников, алерты о новых вакансиях, напоминания о «тишине»
  от компаний (интервалы конфигурируются).

### LLM (`llm/base.py`, `openrouter.py`, `scoring.py`, `letter.py`, `prompt_loader.py`)
- `LLMProvider` — абстракция; реализация `OpenRouterProvider` (DeepSeek).
- **Промпты как код:** `llm/prompts/{scoring,letters,classification}/<category>.md`
  + `default.md` как fallback. Выбор по `profile.category` (в v0.1 заполнен `it`,
  остальные → default).
- **Structured output:** ответы LLM — JSON по pydantic-схеме, ретраи на невалидном
  (`LLM_MAX_RETRIES`), user-поля обрезаются до `LLM_FIELD_MAX_CHARS`.
- **Защита от prompt injection:** user input оборачивается в теги, длина/спецсимволы
  валидируются.
- **Eval-фреймворк:** `tests/eval/golden_dataset.py` — эталонные примеры; регресс-
  тесты в CI идут без вызова LLM.

### Отзывы о компаниях (killer-фича) (`services/company_review.py`)
- Не «отзыв сотрудника», а оценка отношения компании к **кандидатам**.
- Компания идентифицируется нормализованным `company_key` (считается в Python —
  единый источник нормализации).
- **Верификация только через трекер:** оставить отзыв может тот, у кого есть
  `application` к этой компании (в любом статусе). Право определяется по
  пересечению `company_key` отклика и вакансии.
- 5 структурных сигналов + опциональный текст → взвешенный **respect-score 0–100**.
  Один отзыв на компанию от юзера (повторная отправка обновляет).
- **Без жёсткой модерации**, но есть post-hoc авто-скрытие: жалобы
  (`company_review_reports`, идемпотентные по `unique(review_id, user_id)`) при
  достижении порога (`REPORT_HIDE_THRESHOLD=3`) выставляют `is_hidden=true`.
  Скрытый отзыв исчезает из публичных списков/агрегата, но автор видит свой.
- Отзывы анонимны для читателей (без `user_id` в публичном DTO).

### Шаблоны сопроводительных (`services/letter_template.py`)
- CRUD сохранённых шаблонов на профиль (IDOR-проверка через `profiles.user_id`).
- Подстановка `{company}`/`{position}` делается на клиенте; backend хранит сырой текст.

### Трекер откликов (`services/application.py`)
- Статусы `sent → hr → tech → final → offer/reject`, история статусов
  (`application_status_history`) для воронки.
- Заметки, напоминания (`next_reminder_at`), CSV-экспорт, агрегат воронки
  (`/funnel` — counts + conversion_rates).

### Биллинг (`services/` + `api/billing.py`) — стаб
- В beta `beta_mode=true` — всё бесплатно, лимиты не enforced. Заложены эндпоинты
  под Telegram Stars (инвойс/webhook), реализация — v0.2 (см. техдолг).

---

## HTTP API

Базовый префикс — `/api`. Все бизнес-эндпоинты требуют `Authorization: Bearer <JWT>`
(кроме `/auth/*` и `/health*`). Полная интерактивная схема — `GET /docs` (Swagger).

### Health
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | liveness (всегда 200) |
| GET | `/health/ready` | readiness (проверка БД, 503 если недоступна) |

### Auth
| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/telegram` | валидация initData → JWT |
| POST | `/api/auth/dev` | dev-токен без Telegram (локальная разработка) |

### Profiles
| Метод | Путь |
|-------|------|
| GET / POST | `/api/profiles` |
| PATCH / DELETE | `/api/profiles/{id}` |
| POST | `/api/profiles/{id}/activate` |
| GET / PUT | `/api/profiles/{id}/resume` |

### Sources
| Метод | Путь |
|-------|------|
| GET / POST | `/api/profiles/{id}/sources` |
| DELETE | `/api/sources/{id}` |
| POST | `/api/sources/{id}/refresh` |

### Vacancies / Feed
| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/profiles/{id}/feed` | лента (фильтр `reaction`, `limit`, `offset`) |
| GET | `/api/vacancies/{id}` | детали (+ lazy `description_pending`) |
| POST | `/api/vacancies/{id}/reaction` | like / skip / save |
| POST | `/api/vacancies/{id}/score` | оценка через LLM (`force` для пересчёта) |

### Letters / Templates
| Метод | Путь |
|-------|------|
| POST | `/api/vacancies/{id}/letter` |
| GET / PATCH | `/api/letters/{id}` |
| GET | `/api/profiles/{id}/letters` |
| GET / POST | `/api/profiles/{id}/letter-templates` |
| PATCH / DELETE | `/api/letter-templates/{id}` |

### Tracker (Applications)
| Метод | Путь |
|-------|------|
| GET | `/api/profiles/{id}/applications` |
| POST | `/api/applications?profile_id={id}` |
| GET / PATCH | `/api/applications/{id}` |
| GET | `/api/applications/{id}/history` |
| GET | `/api/profiles/{id}/funnel` |
| GET | `/api/profiles/{id}/applications/export` (CSV) |

### Company reviews
| Метод | Путь |
|-------|------|
| GET | `/api/vacancies/{id}/company-review` |
| POST | `/api/vacancies/{id}/company-review?profile_id={id}` |
| POST | `/api/company-reviews/{id}/report` |

---

## Frontend

SPA на React 18 + TS, собирается Vite. Запускается внутри Telegram WebView
(в обычном браузере — dev-fallback на `/api/auth/dev`).

- **Роутинг** (`App.tsx`, React Router 7): защищённые экраны под `Layout` —
  `/feed`, `/tracker`, `/profile`; и отдельные `/vacancies/:id`,
  `/vacancies/:id/letter`, онбординг. Без активного профиля редирект на онбординг.
- **Состояние:** Zustand (`store/auth.ts`) хранит токен/юзера; всё серверное
  состояние — TanStack Query (ключи вида `["feed", profileId]`,
  `["company-review", vacancyId]`, `["letter-templates", profileId]`).
- **API-слой:** `api/client.ts` (axios + интерсептор JWT + `toApiError`),
  `api/endpoints.ts` (тонкие обёртки по доменам), `api/types.ts` (DTO, синхронны с
  backend `schemas.py`).
- **Telegram-интеграция:** `lib/telegram.ts`, `hooks/useBackButton.ts` (нативная
  BackButton привязана к текущему экрану).
- **Чистота lint:** правило `react-refresh/only-export-components` — чистая логика
  выносится в `lib/*` (напр. `lib/companyReview.ts`, `lib/profileForm.ts`).
- **UI-примитивы:** `components/ui.tsx` (Badge с тонами neutral/good/warn/bad,
  Button, Card, Spinner, EmptyState, Skeleton…), тосты — `lib/toast.ts`.

Ключевые экраны: `Feed` (лента + скоринг-бейдж + respect-бейдж компании),
`VacancyDetail` (оценка, реакции, описание, отзывы о компании, письмо/отклик),
`Letter` (генерация + шаблоны), `Tracker` (воронка, статусы, заметки,
кликабельный заголовок → страница вакансии), `Profile`, `Onboarding`.

---

## Модель данных и миграции

Полная DDL-схема (типы, FK, индексы, назначение полей) — в [`CLAUDE.md`](./CLAUDE.md).
Основные таблицы: `users`, `profiles`, `sources`, `vacancies`, `source_vacancies`,
`vacancy_reactions`, `applications`, `application_status_history`, `letters`,
`letter_templates`, `company_reviews`, `company_review_reports`, `payments`,
`events`, `config`.

**Цепочка миграций Alembic** (`backend/alembic/versions/`, линейная `0001 → 0007`):

| Rev | Что добавляет |
|-----|---------------|
| 0001 | Базовая схема: users, profiles, sources, vacancies, reactions, applications, letters, payments, events, config |
| 0002 | `users.notifications_enabled`, `applications.reminder_sent_at` |
| 0003 | `profiles.experience` (фильтр уровней опыта hh.ru) |
| 0004 | `source_vacancies` (link-таблица: результат текущего прогона на источник) |
| 0005 | `company_reviews` (отзывы о компаниях) |
| 0006 | `letter_templates` (шаблоны сопроводительных) |
| 0007 | `company_review_reports` + `company_reviews.is_hidden` (жалобы, авто-скрытие) |

Применить: `uv run alembic upgrade head`. Откат: `uv run alembic downgrade -1`.

> ⚠️ **Важно при деплое.** Образ/деплой должны содержать все файлы миграций.
> Если БД застемплена на ревизию, которой нет в коде контейнера, стартовый
> `alembic upgrade head` падает с `Can't locate revision`. Держите код и миграции
> в одном коммите.

---

## Конфигурация (.env)

Все настройки — из `.env` в корне репозитория (`pydantic-settings`), без хардкода.
Шаблоны: `.env.example` (прод) и `.env.local.example` (локальный docker-стек).
Полный список — в `src/config.py`. Ключевые:

| Переменная | Назначение |
|-----------|-----------|
| `ENV` | `dev` / `prod` (влияет на CORS, формат логов) |
| `DATABASE_URL` | в проде (Railway). Иначе собирается из `DB_HOST/PORT/USER/PASSWORD/NAME` |
| `BOT_TOKEN` | токен бота (@BotFather); им же валидируется initData |
| `JWT_SECRET` | ≥32 символа; подпись JWT |
| `ENCRYPTION_KEY` | base64 от 32 байт; KEK для шифрования резюме |
| `OPENROUTER_API_KEY` | ключ OpenRouter |
| `OPENROUTER_MODEL` | по умолчанию `deepseek/deepseek-chat` |
| `MINIAPP_URL` | публичный HTTPS-URL MiniApp (для inline-кнопки бота) |
| `BACKEND_CORS_ORIGINS` | CSV-whitelist; в prod обязателен, в dev пусто → `*` |
| `PARSER_ENABLED` | включить in-process шедулер (по умолчанию `false`) |
| `PARSER_USE_CHROME` | `true` → headless Chrome, `false` → публичный API |
| `CHROME_BINARY` | путь к Chromium (на Railway/Debian — `/usr/bin/chromium`) |
| `FRONTEND_DIST_PATH` | путь к `frontend/dist` для раздачи SPA самим backend |

Генерация секретов:
```bash
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python -c "import os, base64; print('ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
```

---

## Локальный запуск

### Вариант A: процессы на хосте (для разработки)

```bash
# 0. Секреты
cp .env.example .env   # заполнить (см. выше)

# 1. PostgreSQL
docker compose up -d

# 2. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload --port 8000
# → http://localhost:8000/health · /health/ready · /docs

# 3. Bot (отдельный процесс)
uv run python -m src.bot.main

# 4. Frontend
cd ../frontend
npm install
npm run dev     # → http://localhost:5173 (dev-auth fallback)
```

### Вариант B: единый origin через Docker + ngrok (для теста в Telegram)

`docker-compose.local.yml` поднимает Postgres + backend (раздаёт собранный SPA,
прогоняет миграции на старте) + bot. Backend слушает `:8000`, ngrok даёт один
HTTPS-origin для MiniApp.

```bash
cd frontend && npm install && npm run build && cd ..   # собрать SPA в frontend/dist
cp .env.local.example .env                              # заполнить
docker compose -f docker-compose.local.yml up --build -d
ngrok http 8000 --domain=<ваш-домен>.ngrok-free.dev
# В @BotFather → Mini App URL = https://<ваш-домен>.ngrok-free.dev
```

> Бинарь Chromium для парсера ставится внутрь backend-образа; `CHROME_BINARY`
> и `PARSER_USE_CHROME=true` уже заданы в compose.

---

## Тесты

```bash
cd backend
uv run ruff check .          # линтер
uv run mypy src              # типы
uv run pytest                # unit + integration + eval (без вызова LLM)
uv run pytest -p no:randomly # детерминированный порядок (pytest-randomly)
```

- **unit** (`tests/unit/`) — JWT, шифрование, telegram-auth, парсинг hh, промпты
  скоринга/писем, respect-score отзывов.
- **integration** (`tests/integration/`) — поднимают реальный Postgres,
  `TRUNCATE ... RESTART IDENTITY CASCADE` перед каждым тестом, override
  `get_session`, HTTP через `httpx.ASGITransport` (без сети). Сервисы LLM/парсера —
  через моки (`mocks.py`).
- **eval** (`tests/eval/`) — golden dataset для регресс-тестов промптов (в CI без LLM).

Тесты ожидают, что Alembic уже накатил миграции на тестовую БД.

Frontend:
```bash
cd frontend
npm run lint        # eslint
npm run typecheck   # tsc -b --noEmit
npm run build       # tsc + vite (прод-сборка)
```

---

## CI/CD и деплой

- **CI (GitHub Actions):** backend — ruff + mypy + pytest (с Postgres-сервисом);
  frontend — eslint + tsc + build.
- **Prod (v0.1):** Railway — backend (web) + Postgres + bot (worker, отдельный
  `railway-bot.json`); фронт — Cloudflare Pages. Подробно — `docs/DEPLOYMENT.md`.
- **152-ФЗ:** перед публичным запуском — миграция хостинга в РФ (Selectel/Yandex
  Cloud), согласие на обработку ПД, регистрация оператора.

---

## Безопасность

- **Auth:** Telegram initData (HMAC) → JWT (HS256); TTL initData против replay.
- **Доступ к данным:** каждый сервис проверяет владение ресурсом через
  `profiles.user_id` (защита от IDOR); чужие профили/шаблоны/отзывы → 404.
- **Резюме:** envelope encryption (KEK + per-user DEK, AES-256-GCM); ключ в env.
- **Логи:** без резюме, имён, email, текстов писем — только `telegram_id` и счётчики.
- **LLM:** user input в тегах + инструкция игнорировать вложенные команды; обрезка длины.
- **Платежи:** через Telegram Stars (без карточных данных), идемпотентность по
  `telegram_payment_id` (v0.2).
- **CORS:** в prod обязателен явный whitelist (`BACKEND_CORS_ORIGINS`).

---

## Структура репозитория

```
JobRadar/
├── CLAUDE.md                  # продуктовое видение, DDL-схема, roadmap
├── README.md                  # этот файл
├── docker-compose.yml         # только Postgres (для разработки на хосте)
├── docker-compose.local.yml   # полный локальный стек (Postgres+backend+bot, ngrok)
├── docs/
│   ├── DEPLOYMENT.md
│   └── TECHDEBT.md
├── backend/
│   ├── pyproject.toml         # зависимости, ruff/mypy/pytest конфиг
│   ├── Dockerfile             # + системный Chromium для парсера
│   ├── alembic/versions/      # миграции 0001→0007
│   └── src/
│       ├── main.py            # FastAPI app, роутеры, lifespan, SPA-fallback
│       ├── config.py          # pydantic-settings
│       ├── domain/            # чистые pydantic-модели
│       ├── api/               # роутеры + schemas.py (DTO)
│       ├── services/          # бизнес-логика
│       ├── db/                # models.py + repositories/
│       ├── sources/           # base / hh / hh_chrome
│       ├── llm/               # base / openrouter / scoring / letter / prompts
│       ├── security/          # telegram_auth / jwt / encryption / deps
│       └── bot/               # aiogram 3
│   └── tests/                 # unit / integration / eval / fixtures
└── frontend/
    ├── vite.config.ts · tailwind.config.js
    └── src/
        ├── App.tsx · main.tsx
        ├── api/               # client / endpoints / types
        ├── pages/ · components/ · hooks/ · store/ · lib/
```

---

**Версия:** v0.1 — Closed Beta. Roadmap и продуктовые принципы — в [`CLAUDE.md`](./CLAUDE.md).
