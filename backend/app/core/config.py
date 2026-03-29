# Файл: конфигурация backend-приложения и чтение переменных окружения.

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_database_url(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("postgres://"):
        return "postgresql+psycopg://" + normalized[len("postgres://"):]
    if normalized.startswith("postgresql://") and "postgresql+" not in normalized:
        return "postgresql+psycopg://" + normalized[len("postgresql://"):]
    return normalized


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    cors_origins: str = "*"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        return _normalize_database_url(value)


settings = Settings()
