"""Settings from the environment (``PAP_*``). Validated once at start; invalid combinations refuse to start."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAP_", env_file=None, extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://pap:pap@localhost:5432/pap"

    auth_mode: Literal["oidc", "dev"] = "oidc"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_algorithms: list[str] = Field(default_factory=lambda: ["RS256", "ES256"])
    allow_org_creation: bool = True

    storage_backend: Literal["local"] = "local"
    storage_path: Path = REPO_ROOT / "var" / "artifacts"
    max_upload_bytes: int = Field(default=100 * 1024 * 1024, gt=0)

    engine_lock_path: Path = REPO_ROOT / "engine.lock.json"
    engine_timeout_s: float = Field(default=300.0, gt=0)
    work_path: Path = REPO_ROOT / "var" / "work"

    worker_lease_s: int = Field(default=60, ge=5)
    job_max_attempts: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def _refuse_unsafe_combinations(self) -> Settings:
        if self.env == "production" and self.auth_mode == "dev":
            raise ValueError("PAP_AUTH_MODE=dev is refused when PAP_ENV=production")
        if self.auth_mode == "oidc" and not (self.oidc_issuer and self.oidc_audience):
            raise ValueError("PAP_AUTH_MODE=oidc needs PAP_OIDC_ISSUER and PAP_OIDC_AUDIENCE")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
