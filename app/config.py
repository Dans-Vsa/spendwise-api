"""Application settings loaded from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SPENDWISE_", extra="ignore")

    app_name: str = "SpendWise API"
    environment: str = "development"
    debug: bool = False
    database_url: str = "sqlite:///./spendwise.db"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # JWT auth. Always override the secret outside local development.
    jwt_secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
