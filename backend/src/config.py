"""Конфигурация приложения. Все значения из .env, без хардкода.

Запуск: переменные читаются из .env (см. .env.example в корне проекта).
В тестах можно переопределить через переменные окружения или monkeypatch.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
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

    # --- LLM ---
    openrouter_api_key: str

    # --- Security ---
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 24 * 30  # 30 дней

    # KEK для envelope encryption — base64-encoded 32 байта
    encryption_key: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton настроек. Дёшево в импорте, валидация при первом вызове."""
    return Settings()  # type: ignore[call-arg]


# Удобный модульный доступ: from src.config import settings
settings = get_settings()
