# Деплой JobRadar v0.1

Схема:

```
              ┌─────────────────────────────┐
              │   Cloudflare Pages          │
              │   frontend/ → static        │
              │   https://jobradar.pages.dev│
              └──────────────┬──────────────┘
                             │ HTTPS
                             ▼
              ┌─────────────────────────────────────┐
              │           Railway project           │
              │                                     │
              │   ┌─────────────┐  ┌─────────────┐  │
              │   │  Web (Web)  │  │ Worker (bot)│  │
              │   │  uvicorn    │  │ aiogram     │  │
              │   │ + scheduler │  │ long-poll   │  │
              │   └──────┬──────┘  └──────┬──────┘  │
              │          └────────┬───────┘         │
              │                   ▼                 │
              │           ┌──────────────┐          │
              │           │  Postgres 16 │          │
              │           │  (managed)   │          │
              │           └──────────────┘          │
              └─────────────────────────────────────┘
                             ▲
                             │ Telegram WebApp Mini App URL
              ┌──────────────┴──────────────┐
              │       @BotFather settings   │
              │   /mybots → Configure Mini  │
              │   App → https://jobradar.…  │
              └─────────────────────────────┘
```

## Что нужно перед началом

- GitHub-репо `hitprim/JobRadar` (есть)
- Railway аккаунт (https://railway.app — Sign in with GitHub)
- Cloudflare аккаунт (https://dash.cloudflare.com — бесплатный план)
- @BotFather → создан бот → получен `BOT_TOKEN`
- OpenRouter API ключ (https://openrouter.ai/keys)
- ENCRYPTION_KEY и JWT_SECRET — генерируем в шаге 1

---

## Шаг 1. Сгенерировать секреты (один раз)

В терминале:

```powershell
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(64))"
python -c "import os, base64; print('ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
```

**ВАЖНО:** `ENCRYPTION_KEY` нельзя менять после первого деплоя — иначе все
зашифрованные резюме станут недоступны. Сохрани в надёжном месте (1Password /
запиши).

---

## Шаг 2. Railway: создать проект

1. https://railway.app → **New Project** → **Deploy from GitHub repo** → `hitprim/JobRadar`.
2. Railway автоматически найдёт `backend/Dockerfile` и `backend/railway.json` —
   создаст первый service. Назови его **`backend-web`**.
3. В настройках service:
   - **Settings → Source → Root Directory** = `backend`
   - **Settings → Networking → Generate Domain** (получишь `xxx.up.railway.app`)
4. Создай **Postgres**: в проекте **+ New → Database → PostgreSQL**.
   Railway автоматически создаст переменную `DATABASE_URL` и привяжет к проекту.

### Environment-переменные для `backend-web`

В **backend-web → Variables** добавь:

```
ENV=prod

# DATABASE_URL ← Railway инжектит автоматически через "Reference Variable"
# (выбери из переменных Postgres-сервиса)
DATABASE_URL=${{Postgres.DATABASE_URL}}

BOT_TOKEN=<from-BotFather>
OPENROUTER_API_KEY=<from-openrouter.ai>

JWT_SECRET=<generated-step-1>
ENCRYPTION_KEY=<generated-step-1>

# CORS — точный домен Cloudflare Pages (см. шаг 5)
BACKEND_CORS_ORIGINS=https://jobradar.pages.dev

# MiniApp URL для inline-кнопки бота (тот же что в @BotFather)
MINIAPP_URL=https://jobradar.pages.dev

# Scheduler — включаем парсинг hh.ru + уведомления + reminders
PARSER_ENABLED=true
PARSER_INTERVAL_MINUTES=60
ALERTS_INTERVAL_MINUTES=60
REMINDERS_INTERVAL_MINUTES=15

# hh.ru User-Agent: твой контактный email
HH_USER_AGENT_CONTACT=you@example.com
```

5. **Deploy** → Railway соберёт Docker, применит миграции через `preDeployCommand`
   (`alembic upgrade head`), запустит uvicorn.
6. Проверь: открой `https://<your-backend>.up.railway.app/health` →
   должно быть `{"status":"ok"}`. И `/health/ready` → `{"status":"ready","db":"ok"}`.

---

## Шаг 3. Railway: добавить worker (бот)

1. В том же проекте: **+ New → Empty Service** → назови **`backend-bot`**.
2. **Settings → Source → Connect Repo** → `hitprim/JobRadar`, **Root Directory** = `backend`.
3. **Settings → Deploy → Custom Start Command** = `python -m src.bot.main`
4. **Settings → Networking** — ничего не выставляй (бот не принимает HTTP).
5. **Variables** — те же что у `backend-web` (можно скопировать через "Reference
   Variable" из backend-web). **DATABASE_URL** обязательно один и тот же.
6. **Deploy**. Логи должны показать `JobRadar bot starting (long-polling)`.

---

## Шаг 4. Cloudflare Pages: frontend

1. https://dash.cloudflare.com → **Workers & Pages** → **Create application** →
   **Pages** → **Connect to Git** → выбери `hitprim/JobRadar`.
2. Build settings:
   - **Framework preset**: Vite
   - **Build command**: `npm run build`
   - **Build output directory**: `dist`
   - **Root directory**: `frontend`
3. **Environment variables** (Production):
   ```
   VITE_API_BASE_URL=https://<your-backend>.up.railway.app/api
   ```
4. **Save and Deploy**. После сборки получишь `https://jobradar-xyz.pages.dev`.

5. Если домен Cloudflare Pages отличается от того, что ты указал в
   `BACKEND_CORS_ORIGINS` (шаг 2) и `MINIAPP_URL` — вернись и поправь
   на Railway.

---

## Шаг 5. @BotFather: подключить Mini App

1. В Telegram: @BotFather → `/mybots` → выбери бота → **Bot Settings → Menu Button**
   → **Configure menu button** → URL = `https://<your-frontend>.pages.dev`,
   текст кнопки `Открыть JobRadar`.
2. Также **Configure Mini App** → тот же URL.

---

## Шаг 6. Проверка end-to-end

1. Открой бота в Telegram.
2. `/start` → должно прийти сообщение с inline-кнопкой "Открыть JobRadar".
3. Кликни → откроется WebApp → должно появиться **Onboarding** (создание профиля).
4. Заполни → создай профиль → попадёшь в **Feed** (пока пусто).
5. На бэкенде scheduler через ~1 час сделает первый парсинг hh.ru → в боте
   придёт уведомление "🔔 Найдено новых вакансий: N".
6. Ручной refresh: нажми "⟳ Обновить" в Feed → сразу подтянет вакансии.

---

## Troubleshooting

### Backend не стартует, лог "ValueError: BACKEND_CORS_ORIGINS must be set"
ENV=prod требует явный whitelist. Проверь что переменная задана и непустая.

### Frontend получает CORS-ошибку
Cloudflare Pages URL должен быть в `BACKEND_CORS_ORIGINS` 1-в-1
(включая `https://`, без trailing `/`).

### Бот не отвечает на `/start`
Проверь логи `backend-bot` в Railway. Скорее всего:
- `BOT_TOKEN` не задан или неверный → 401 от Telegram API
- conflict polling: убедись что нет второго инстанса (локально / другого деплоя)
  с тем же токеном.

### Migrations не применились
`preDeployCommand` упал — смотри Deploy Logs последней деплойки. Часто:
- `DATABASE_URL` некорректный (старый формат `postgres://` — мы конвертируем,
  но проверь reference на Postgres service в Railway).

### Resume не открывается ("InvalidCiphertextError")
`ENCRYPTION_KEY` изменился между деплоями. Восстанови старый ключ —
данные нельзя расшифровать другим.

---

## Откатить деплой

Railway → backend-web → **Deployments** → клик по предыдущему успешному →
**Redeploy**. То же для `backend-bot`.

Migrations rollback: `uv run alembic downgrade -1` локально → проверить → задеплоить
изменения в коде. Railway сам не откатывает миграции.

---

## 152-ФЗ pre-launch checklist

В v0.1 (closed beta для 5-20 знакомых) — Railway хватает.

Перед публичным запуском:
- Миграция на Selectel/Yandex Cloud (российский хостинг)
- Регистрация оператора ПД в Роскомнадзоре
- Политика конфиденциальности + оферта на сайте
- Согласие на обработку ПД при онбординге
