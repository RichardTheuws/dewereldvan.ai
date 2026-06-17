"""Application settings, loaded from environment (.env) via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://app:app@postgres:5432/dewereldvan"
    secret_key: str  # REQUIRED, no default — session signing + token salt
    base_url: str = "https://dewereldvan.ai"
    email_backend: str = "console"  # "console" | "resend"
    resend_api_key: str | None = None
    email_from: str = "dewereldvan.ai <noreply@dewereldvan.ai>"
    magic_link_ttl_min: int = 15
    pending_expiry_days: int = 14
    admin_emails: str = ""  # comma-separated; bootstrap admin role on approval/login
    session_max_age_sec: int = 60 * 60 * 24 * 14  # 14d signed cookie
    console_email_dir: str = "data/outbox"
    rate_limit_magic_per_hour: int = 5
    # Max anonymous open registrations accepted per source IP per hour.
    rate_limit_register_per_hour: int = 5

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


# Module singleton; deps import this. Tests override via env in conftest.
settings = Settings()
