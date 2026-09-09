"""Application settings.

All configuration is environment-driven (12-factor). See `.env.example` at the
repo root for the full documented set of variables.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App -------------------------------------------------------------
    app_name: str = "AoE2 Lab API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    log_level: str = "INFO"

    # --- Database --------------------------------------------------------
    database_url: str = "postgresql+psycopg://aoe2:aoe2@localhost:5432/aoe2"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- Redis -----------------------------------------------------------
    # Optional. Used for the replay-processing queue and response caching; every
    # caller degrades gracefully when it is unavailable.
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 900

    # --- Replay processing ------------------------------------------------
    replay_storage_path: str = "/data/replays"
    max_replay_size_mb: int = 100
    replay_parser_timeout_seconds: int = 300

    # --- Analysis ---------------------------------------------------------
    # Feature version is stamped onto every derived metric row so that a change
    # to a calculation never silently invalidates historical analyses.
    analytics_feature_version: int = 1

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Allow `A,B,C` in env vars as well as JSON lists."""
        if isinstance(v, str) and not v.strip().startswith("["):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @property
    def max_replay_size_bytes(self) -> int:
        return self.max_replay_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
