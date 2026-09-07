"""Application settings.

All configuration is environment-driven (12-factor). See `.env.example` at the repo
root for the full documented set of variables.
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
    app_name: str = "Rift Lab API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    log_level: str = "INFO"

    # --- Database --------------------------------------------------------
    database_url: str = "postgresql+psycopg://riftlab:riftlab@localhost:5432/riftlab"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- Redis -----------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 900

    # --- Riot API --------------------------------------------------------
    riot_api_key: str = ""
    # When true (or when no API key is present) the app serves a deterministic
    # synthetic dataset instead of calling Riot. Everything downstream — ingestion,
    # feature engineering, ML — is identical, which keeps the project runnable and
    # testable without credentials.
    riot_use_mock: bool = True
    riot_platform: str = "na1"
    riot_timeout_seconds: float = 10.0
    riot_max_retries: int = 4
    # Riot personal-key defaults. Production keys get much higher ceilings; both
    # windows are enforced together by the sliding-window limiter.
    riot_rate_limit_short: int = 20  # requests per `riot_rate_limit_short_window`
    riot_rate_limit_short_window: int = 1  # seconds
    riot_rate_limit_long: int = 100
    riot_rate_limit_long_window: int = 120

    # --- Ingestion -------------------------------------------------------
    ingest_default_match_count: int = 30
    ingest_max_match_count: int = 200
    ingest_queue_ids: list[int] = Field(default_factory=lambda: [420, 440, 400])
    ingest_concurrency: int = 4

    # --- ML --------------------------------------------------------------
    model_dir: str = "/app/models"
    skill_gap_min_samples: int = 200
    risk_model_grid_size: int = 32
    risk_horizon_seconds: int = 30

    @field_validator("cors_origins", "ingest_queue_ids", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Allow `A,B,C` in env vars as well as JSON lists."""
        if isinstance(v, str) and not v.strip().startswith("["):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            return parts
        return v

    @property
    def use_mock_riot(self) -> bool:
        return self.riot_use_mock or not self.riot_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
