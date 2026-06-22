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
    # Een los, gemonitord contactadres voor de neutrale herstel-route ("klopt er
    # iets niet? mail ons") — zodat een vals geblokkeerd mens een uitweg heeft zonder
    # ooit "niet geschikt" te horen. NIET het persoonlijke admin-adres (operator
    # communiceert via Telegram). Leeg = de regel wordt niet getoond. Zet CONTACT_EMAIL
    # op M4 als je een gemonitord support-adres hebt.
    contact_email: str = ""
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
    # Goedkoop, snel model voor de spam-triage bij registratie (pivot Fase B) — een
    # lichte mens-of-bot-beoordeling, geen reden voor het dure Opus-model.
    triage_model: str = "claude-haiku-4-5-20251001"  # TRIAGE_MODEL
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
    # Tool-review-correctie/aanvulling (doc 03 §4.3, mens-naast-AI) — per lid,
    # glijdend uur-venster (spiegelt rate_limit_idea_per_hour). Iets ruimer: een
    # expert vult soms meerdere velden van één tool tegelijk aan.
    rate_limit_tool_note_per_hour: int = 8  # per lid
    # Agenda/nieuws plaatsen (Post) — per lid, glijdend uur-venster, over events
    # en nieuws samen. Iets ruimer dan ideeën: een lid voegt soms een reeks
    # meetups/artikelen tegelijk toe.
    rate_limit_post_per_hour: int = 10  # per lid
    # Intro's/connecties versturen (Tier 1 Fase 2) — per lid, glijdend uur-venster.
    # Krap gehouden: een intro mailt een ander lid; dit dempt spam/ongewenste post.
    rate_limit_intro_per_hour: int = 8  # per lid
    # De publieke MCP-server-URL (eigen Cloudflare-ingress, los van base_url). Wordt
    # getoond in het `claude mcp add`-commando op de "verbind je tool"-pagina.
    mcp_base_url: str = "https://mcp.dewereldvan.ai"  # MCP_BASE_URL
    # Telegram-notificatiekanaal (lid-gekozen push). Gegate: zonder token is het
    # kanaal niet beschikbaar (de UI toont 'binnenkort'). De webhook-secret valideert
    # dat een /telegram/webhook-call écht van Telegram komt (secret-token-header).
    telegram_bot_token: str | None = None  # TELEGRAM_BOT_TOKEN (@BotFather)
    telegram_bot_username: str | None = None  # TELEGRAM_BOT_USERNAME (voor de deep-link)
    telegram_webhook_secret: str | None = None  # TELEGRAM_WEBHOOK_SECRET
    # Harde bovengrens op de body-lengte van een feedback-bericht (anti-abuse;
    # geldt voor zowel ingelogde als anonieme inzending).
    max_feedback_body_chars: int = 4000

    # --- Bezoeker-AI-kostengovernance (Fase 1, doc 04 §4.2) ---
    # Cloudflare Turnstile (mens-bewijs per betaalde niet-lid-call). Zonder
    # secret-key is het hele niet-lid-AI-pad UIT (veilige default: geen sleutels
    # = geen onbedoelde spend); spiegelt hoe Telegram zonder token gegate is.
    turnstile_site_key: str | None = None  # TURNSTILE_SITE_KEY (publiek, in de widget)
    turnstile_secret_key: str | None = None  # TURNSTILE_SECRET_KEY (server-side verify)
    # Per-bezoeker daglimiet (rij-tel 24u op visitor_id).
    visitor_ai_calls_per_day: int = 3
    # Per-IP daglimiet (grover vangnet voor cookie-wissers).
    visitor_ai_calls_per_ip_per_day: int = 20
    # Globale weekcap — de wiskundige garantie: som(cost) lopende ISO-week
    # + voorschat > budget → geen call.
    visitor_ai_budget_eur_per_week: float = 50.0
    # Anti-burst: minimaal aantal seconden tussen twee calls van één bezoeker.
    visitor_ai_min_seconds_between_calls: int = 30
    # TTL van de identieke-prompt-cache (identieke prompt binnen TTL → €0, geen call).
    visitor_ai_prompt_cache_ttl_hours: int = 24
    # Modelprijs (Opus 4.8, doc §3) voor de kostberekening uit token-usage.
    # In euro per miljoen tokens; bevroren per rij in cost_eur_micros.
    ai_price_input_eur_per_mtok: float = 4.65
    ai_price_output_eur_per_mtok: float = 23.25

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def support_contact(self) -> str:
        """Het adres voor de neutrale herstel-route. ALLEEN een expliciet gezet
        ``contact_email`` — valt NOOIT terug op het persoonlijke admin-adres (de
        operator communiceert via Telegram, niet via z'n eigen mail). Leeg = de
        herstel-regel wordt niet getoond (geen mail-adres gelekt)."""
        return self.contact_email.strip()

    @property
    def allowed_image_type_set(self) -> set[str]:
        return {
            t.strip().lower()
            for t in self.allowed_image_types.split(",")
            if t.strip()
        }


# Module singleton; deps import this. Tests override via env in conftest.
settings = Settings()
