"""Settings from the environment (``PAP_*``). Validated once at start; invalid combinations refuse to start."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class EnvironmentConfig(BaseModel):
    """An execution environment the operator allows workspaces to connect (D-026). Users pick from these; the API
    never contacts a URL a user typed."""

    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["simulated", "physical"]
    adapter: Literal["wot-http"] = "wot-http"
    endpoint: str = Field(pattern=r"^https?://[^\s/]+(/[^\s]*)?$")
    description: str = ""


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

    storage_backend: Literal["local", "s3"] = "local"
    storage_path: Path = REPO_ROOT / "var" / "artifacts"
    max_upload_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    # S3-compatible storage (PAP_STORAGE_BACKEND=s3). Credentials: standard AWS_* variables or the instance role.
    s3_bucket: str | None = None
    s3_prefix: str = ""
    s3_endpoint_url: str | None = None  # unset = AWS; set for SeaweedFS, MinIO, Ceph, R2, ...
    s3_region: str = "us-east-1"
    s3_path_style: bool = True

    engine_lock_path: Path = REPO_ROOT / "engine.lock.json"
    engine_timeout_s: float = Field(default=300.0, gt=0)
    work_path: Path = REPO_ROOT / "var" / "work"

    # Execution environments (JSON list in PAP_ENVIRONMENTS). Empty: no environment can be connected.
    environments: list[EnvironmentConfig] = Field(default_factory=list)
    device_timeout_s: float = Field(default=10.0, gt=0, le=120)
    workflow_step_timeout_s: float = Field(default=60.0, gt=0, le=3600)

    worker_lease_s: int = Field(default=60, ge=5)
    job_max_attempts: int = Field(default=3, ge=1, le=10)

    # /metrics on the API: open outside production; in production only with this bearer token (else 404).
    metrics_token: str | None = None
    # The worker serves its own /metrics on this port when set (job durations and engine metrics live there).
    worker_metrics_port: int | None = Field(default=None, ge=1, le=65535)

    @model_validator(mode="after")
    def _refuse_unsafe_combinations(self) -> Settings:
        if self.env == "production" and self.auth_mode == "dev":
            raise ValueError("PAP_AUTH_MODE=dev is refused when PAP_ENV=production")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("PAP_STORAGE_BACKEND=s3 needs PAP_S3_BUCKET")
        if self.auth_mode == "oidc" and not (self.oidc_issuer and self.oidc_audience):
            raise ValueError("PAP_AUTH_MODE=oidc needs PAP_OIDC_ISSUER and PAP_OIDC_AUDIENCE")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
