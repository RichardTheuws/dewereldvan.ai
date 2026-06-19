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

    # --- Profielfoto-upload (L1) ---
    # Opslag-subdir onder het /app/data-volume (geen apart volume nodig).
    upload_dir: str = "data/uploads"  # UPLOAD_DIR
    upload_url_prefix: str = "/uploads"  # serveer-pad (StaticFiles-mount)
    max_upload_bytes: int = 6 * 1024 * 1024  # 6 MB hard cap (server-hervalidatie)
    allowed_image_types: str = "image/jpeg,image/png,image/webp"
    photo_output_px: int = 512  # vierkante crop-zijde (ronde weergave via CSS)
    rate_limit_photo_per_hour: int = 12  # per lid

    # --- Ervaring-laag (E1-E4): feedback, ideeenbus, roadmap ---
    # Anti-spam per ingelogd lid in een glijdend uur-venster (rij-tel-patroon,
    # spiegelt rate_limit_magic_per_hour). Anonieme feedback wordt per inzender-IP
    # begrensd (zie rate_limit_feedback_anon_per_hour), niet via deze per-lid teller.
    rate_limit_feedback_per_hour: int = 12  # per lid
    # Anonieme (uitgelogde) feedback per inzender-IP in een glijdend uur-venster
    # (zelfde rij-tel-patroon op de feedback.ip-kolom). Sluit de ongebonden
    # anonieme schrijf (storage-DoS) zonder het anonieme pad te schrappen.
    rate_limit_feedback_anon_per_hour: int = 6  # per IP
    rate_limit_idea_per_hour: int = 6  # per lid
    # Agenda/nieuws plaatsen (Post) — per lid, glijdend uur-venster, over events
    # en nieuws samen. Iets ruimer dan ideeën: een lid voegt soms een reeks
    # meetups/artikelen tegelijk toe.
    rate_limit_post_per_hour: int = 10  # per lid
    # Harde bovengrens op de body-lengte van een feedback-bericht (anti-abuse;
    # geldt voor zowel ingelogde als anonieme inzending).
    max_feedback_body_chars: int = 4000

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def allowed_image_type_set(self) -> set[str]:
        return {
            t.strip().lower()
            for t in self.allowed_image_types.split(",")
            if t.strip()
        }


# Module singleton; deps import this. Tests override via env in conftest.
settings = Settings()
