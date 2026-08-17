"""Environment-backed application dependencies."""

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentMode(StrEnum):
    """Supported runtime environments."""

    DEV = "dev"
    PROD = "prod"


class Settings(BaseSettings):
    """Newman Labs runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_assignment=True,
    )

    environment: EnvironmentMode = EnvironmentMode.DEV
    log_level: str = "INFO"
    # Public identifier rendered client-side for Cloudflare Web Analytics.
    cloudflare_web_analytics_site_id: str = "faa3fce72b41494785f1cb472513d56a"


settings = Settings()
