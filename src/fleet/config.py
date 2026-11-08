"""Settings (from the environment) and configuration (from configs/config.yaml).

Secrets and connection strings only ever come from environment variables, never from the YAML file.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLEET_", env_file=".env", extra="ignore")

    config_path: Path = ROOT / "configs" / "config.yaml"
    data_dir: Path = ROOT / "data"
    artifacts_dir: Path = ROOT / "artifacts"

    kafka_bootstrap: str = "localhost:29092"
    database_url: str = "postgresql://fleet:fleet_dev_only@localhost:5433/fleet"

    oidc_issuer: str = "http://localhost:8080/realms/fleet"
    oidc_jwks_url: str = "http://localhost:8080/realms/fleet/protocol/openid-connect/certs"
    oidc_audience: str = "fleet-api"


@lru_cache
def settings() -> Settings:
    return Settings()


@lru_cache
def config() -> dict[str, Any]:
    path = Path(os.environ.get("FLEET_CONFIG_PATH", settings().config_path))
    return yaml.safe_load(path.read_text(encoding="utf-8"))
