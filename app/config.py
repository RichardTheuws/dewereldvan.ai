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
    email_backend: str = "console"  # "console" | "resend" | "cloudflare"
    resend_api_key: str | None = None
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None  # needs "Email Sending: Edit" permission
    email_from: str = "dewereldvan.ai <noreply@dewereldvan.ai>"
    magic_link_ttl_min: int = 15
    pending_expiry_days: int = 14
    admin_emails: str = ""  # comma-separated; bootstrap admin role on approval/login
    session_max_age_sec: int = 60 * 60 * 24 * 14  # 14d signed cookie
    console_email_dir: str = "data/outbox"
    rate_limit_magic_per_hour: int = 5
    # Max anonymous open registrations accepted per source IP per hour.
    rate_limit_register_per_hour: int = 5

    # --- AI-native profielbouw (F1-F3) ---
    # The anthropic SDK reads ANTHROPIC_API_KEY from env itself; we also expose it
    # here so settings stay the single source of truth for config introspection.
    anthropic_api_key: str | None = None  # ANTHROPIC_API_KEY
    anthropic_model: str = "claude-opus-4-8"  # ANTHROPIC_MODEL
    fal_key: str | None = None  # FAL_KEY — fal.ai cover generation
    ai_enrich_enabled: bool = True  # AI_ENRICH_ENABLED
    rate_limit_ai_enrich_per_hour: int = 10  # per lid
    # Factory switch for the ImageGenerator backend (net als email_backend).
    ai_image_backend: str = "fal"  # "fal" | "noop"

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


# Module singleton; deps import this. Tests override via env in conftest.
settings = Settings()
