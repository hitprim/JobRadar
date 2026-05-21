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
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "jobradar"
    db_password: str
    db_name: str = "jobradar"

    # --- Telegram ---
    bot_token: str
    # Срок жизни поля auth_date в initData (защита от replay).
    init_data_ttl_seconds: int = 24 * 60 * 60  # 24 часа

    # --- LLM ---
    openrouter_api_key: str

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
    # Сколько вакансий тянуть за один прогон парсера (на источник).
    parser_max_pages: int = 5
    parser_per_page: int = 50
    # Период публикации (дни) для запросов к hh.ru. По умолчанию 7 дней.
    parser_period_days: int = 7
    # Тайм-аут запроса к hh.ru
    parser_http_timeout_seconds: float = 10.0
    # Контактный email (требуется для User-Agent в запросах к hh.ru API)
    hh_user_agent_contact: str = "jobradar@example.com"

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
