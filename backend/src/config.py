"""Конфигурация приложения. Все значения из .env, без хардкода.

Запуск: переменные читаются из .env (см. .env.example в корне проекта).
В тестах можно переопределить через переменные окружения или monkeypatch.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",  # backend/ запускается из своей папки, .env в корне репо
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "prod"] = "dev"

    # --- PostgreSQL ---
    # В prod: Railway инжектит DATABASE_URL — используем его как есть.
    # В dev: собираем из DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME.
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "jobradar"
    db_password: str = "change-me"
    db_name: str = "jobradar"

    # --- Telegram ---
    bot_token: str
    # Срок жизни поля auth_date в initData (защита от replay).
    init_data_ttl_seconds: int = 24 * 60 * 60  # 24 часа
    # URL MiniApp для inline-кнопки в боте. Пусто = кнопка не показывается.
    # В prod ставим публичный HTTPS URL (зарегистрированный в @BotFather).
    miniapp_url: str = ""

    # --- LLM ---
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "deepseek/deepseek-chat"
    openrouter_timeout_seconds: float = 30.0
    # Сколько раз ретраить при невалидном JSON-ответе или 5xx
    llm_max_retries: int = 2
    # Максимальная длина одного user-поля (резюме, описание вакансии) в символах
    # — обрезаем перед отправкой в LLM, чтобы не упереться в context window
    llm_field_max_chars: int = 12_000

    # --- Security ---
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 24 * 30  # 30 дней

    # KEK для envelope encryption — base64-encoded 32 байта
    encryption_key: str

    # --- Parser / hh.ru ---
    hh_api_base_url: str = "https://api.hh.ru"
    # In-process scheduler: по умолчанию ВЫКЛЮЧЕН.
    # В prod включается явно. Ручной refresh через POST /sources/{id}/refresh работает всегда.
    parser_enabled: bool = False
    parser_interval_minutes: int = 60
    # Интервалы для notification-job'ов (тот же scheduler, тот же PARSER_ENABLED флаг).
    alerts_interval_minutes: int = 60
    reminders_interval_minutes: int = 15
    # Сколько вакансий тянуть за один прогон парсера (на источник).
    parser_max_pages: int = 5
    parser_per_page: int = 50
    # Период публикации (дни) для запросов к hh.ru. По умолчанию 7 дней.
    parser_period_days: int = 7
    # Тайм-аут запроса к hh.ru
    parser_http_timeout_seconds: float = 10.0
    # Контактный email (требуется для User-Agent в запросах к hh.ru API)
    hh_user_agent_contact: str = "jobradar@example.com"

    # --- Headless Chrome парсер (обход антибота, без CDP) ---
    # Переключатель источника "hh": True → HhChromeSource (headless Chrome --dump-dom),
    # False → старый HhSource (публичный API, сейчас отдаёт 403).
    parser_use_chrome: bool = True
    # Путь к бинарю Chrome/Chromium. Пусто → автоопределение по списку кандидатов.
    # На Railway (Debian) обычно "/usr/bin/chromium".
    chrome_binary: str = ""
    # Базовый URL веб-морды hh.ru (НЕ api.). Отсюда строим /search/vacancy.
    hh_web_base_url: str = "https://hh.ru"
    # Сколько headless-Chrome процессов одновременно (память!). 1 страница ≈ 1 процесс.
    parser_concurrency: int = 3
    # Тайм-аут одного запуска Chrome (рендер SPA + dump). Kill по истечении.
    # hh.ru — тяжёлая SPA; в контейнере (особенно Docker Desktop/WSL2) полный
    # рендер выдачи занимает ~45-55s. 30s было мало → таймаут. Держим с запасом.
    parser_chrome_timeout_seconds: float = 75.0
    # virtual-time-budget для Chrome (мс) — сколько ждать выполнения JS перед дампом.
    parser_chrome_virtual_time_ms: int = 8000
    # Прокси для Chrome (--proxy-server). Пусто → без прокси (IP машины — потолок).
    parser_proxy_server: str = ""
    # Джиттер между страницами (сек) — рандомная задержка, чтобы не долбить ровным ритмом.
    parser_jitter_min_seconds: float = 1.5
    parser_jitter_max_seconds: float = 6.0
    # Ретраи при блокировке/таймауте Chrome (экспоненциальный бэкофф).
    parser_chrome_max_retries: int = 2

    # --- Frontend (локальная раздача SPA самим backend'ом) ---
    # Путь к собранному фронту (frontend/dist). Пусто → SPA НЕ раздаётся
    # (в проде фронт на Cloudflare/Netlify, backend отдаёт только /api).
    # Для локального ngrok-деплоя задаём путь — тогда один origin отдаёт и SPA, и API.
    frontend_dist_path: str = ""

    # --- CORS ---
    # CSV-список origin'ов. В dev пустой → разрешаем всем ('*').
    # В prod обязателен непустой whitelist (валидируется при старте, см. ниже).
    backend_cors_origins: str = ""

    @field_validator("backend_cors_origins")
    @classmethod
    def _strip_cors(cls, v: str) -> str:
        return v.strip()

    @property
    def database_url(self) -> str:
        """Возвращает SQLAlchemy async URL.

        - Если задан DATABASE_URL (Railway/CI) — нормализуем драйвер
          `postgres://` или `postgresql://` → `postgresql+asyncpg://`.
        - Иначе собираем из DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME.
        """
        if self.database_url_override:
            raw = self.database_url_override
            for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
                if raw.startswith(prefix):
                    rest = raw[len(prefix) :]
                    return f"postgresql+asyncpg://{rest}"
            return raw  # неизвестный формат — отдаём как есть, SQLA скажет
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def cors_origins(self) -> list[str]:
        """Парсит backend_cors_origins в список.

        Правила:
        - dev + пусто → ["*"] (удобство локальной разработки)
        - prod + пусто → исключение (явный whitelist обязателен)
        - непустая строка → CSV split, trim, пустые пропускаем
        """
        raw = self.backend_cors_origins
        if not raw:
            if self.is_dev:
                return ["*"]
            raise ValueError(
                "BACKEND_CORS_ORIGINS must be set in production "
                "(comma-separated whitelist of allowed origins)"
            )
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton настроек. Дёшево в импорте, валидация при первом вызове."""
    return Settings()  # type: ignore[call-arg]


# Удобный модульный доступ: from src.config import settings
settings = get_settings()
