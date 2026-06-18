# Changelog

Alle noemenswaardige wijzigingen aan dit project worden hier vastgelegd.
Volgt [Keep a Changelog](https://keepachangelog.com/) en [SemVer](https://semver.org/).

## [0.8.1] - 2026-06-18
### Security
- Stored XSS gedicht: `safe_url`-Jinja-filter (alleen `http`/`https`/relatief)
  toegepast op AI/pagina-geleverde `url`/`image_url`/`cover_image_url` in
  `_cosmic_link_card.html`, `_cosmic_project_card.html` en `view.html` — blokkeert
  `javascript:`/`data:`-schema's in `href`/`src` op het publieke profiel.
- DOM-XSS via de live SSE-stream gedicht: elke assistant-delta wordt server-side
  HTML-geëscaped (`markupsafe.escape`) vóór het `delta`-event, zodat de live-bubbel
  als tekst rendert (sluit het prompt-injection→XSS-pad en de markup-flash).
- AVG-scope afgedwongen: `web_fetch` wordt beperkt tot de door het lid geplakte
  domeinen (`allowed_domains`) en `web_search` vervalt zodra er links zijn; system-
  prompt herhaalt dat opgehaalde paginacontent gegevens zijn, geen instructies.

### Fixed
- AVG-retentie: `POST /profiel/ai/opnieuw` wist nu ook `ai_source_text` en de in de
  sessie gegenereerde `cover_image_url` (de knop beloofde dat al).
- Publiek profiel is zonder JS zichtbaar: `<noscript>`-vangnet forceert
  `[data-reveal]`-content zichtbaar (progressive enhancement i.p.v. JS-gate).
- A11y: streamende assistant-bubbel krijgt `aria-live="polite"`; typing-indicator
  krijgt `role="status"` + visueel-verborgen label.
- Opschoning: SSE-drain-protocol (sentinel + timeout) leeft nu uitsluitend in
  `_Channel.get`; de router-duplicatie (`_blocking_get`, dubbele `_DONE`-import,
  tweede `120.0`) is verwijderd.

## [0.8.0] - 2026-06-18
### Added (AI-native profielbouw — ROUTES+UI, F1-F3)
- Router-bodies in `app/routers/ai_profile.py`: `GET /profiel/ai/bouwen` (kosmische
  chat-bouwpagina), `POST /profiel/ai/bericht` (persist user-turn + SSE-container),
  `GET /profiel/ai/stream` (SSE: tekst-deltas + `done`-bubbel; sync SDK in threadpool,
  refusal-veilig), `POST /profiel/ai/maak-draft` (structured output → DRAFT zonder
  `visibility` te zetten), `POST /profiel/ai/cover` (F2, faalt gracieus),
  `POST /profiel/ai/draft/bewerken`, `POST /profiel/ai/publiceren` (delegeert naar de
  bestaande zichtbaarheidsflow; consent vereist voor public), `POST /profiel/ai/opnieuw`.
- `app/services/ai_conversation.py`: DB-conversatie-state (`load_messages` /
  `append_turn` / `clear_turns` / `has_turns`) + in-process SSE-`_Channel`.
- Kosmische identiteit: `app/static/cosmic.css` (tokens + nebula/gloed/sterren/grain,
  Fraunces + JetBrains Mono + Spline Sans, `prefers-reduced-motion`-veilig);
  `base.html` (fonts + cosmic.css + htmx-sse + "Bouw met AI"-nav).
- Herontworpen publieke profielpagina `profiles/view.html` (kosmische diepte; cover-hero,
  headline/bio/rollen/projects-met-beeld/seeking/tags; OG-tags alléén voor public;
  noindex + login-gating gerespecteerd) + partials (`_cosmic_bg`, `_cosmic_link_card`,
  `_cosmic_project_card`, `_cosmic_tags`).
- Bouwflow-templates (`ai/build.html`, `_chat_message`, `_message_sent`, `_draft_preview`,
  `_draft_card_link`, `_cover`, `_cosmic_canvas`).

## [0.7.0] - 2026-06-18
### Added (AI-native profielbouw — FOUNDATION, F1-F3)
- Datamodel (additief, breekt geen bestaande tabellen): `profile` krijgt `headline`,
  `cover_image_url`, `ai_enriched`, `ai_source_text`; `offering` krijgt `url`, `image_url`;
  nieuw `ProfileLink`-model (`profile_link`: rollen/affiliaties + builds met beeld) en
  `AiChatTurn`-model (`ai_chat_turn`: server-side conversatie-state). Migratie
  `0003_ai_profile` (strikt additief; up+down geverifieerd).
- Enum `ProfileLinkKind` (`native_enum=False` → VARCHAR + CHECK, SQLite/Postgres-pariteit).
- `ImageGenerator`-interface (`app/ai/`): `Protocol` + `FalImageGenerator` (fal.ai flux/schnell
  via httpx, faalt gracieus → `url=None`) + `NoopImageGenerator` (fallback) + factory
  `get_image_generator()` via settings; deps-injectie `image_generator()` (overridable in tests).
- Config: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-opus-4-8`), `FAL_KEY`,
  `AI_ENRICH_ENABLED`, `RATE_LIMIT_AI_ENRICH_PER_HOUR`, `AI_IMAGE_BACKEND`; `.env.example` bijgewerkt.
- `requirements.txt`: `anthropic==0.69.0`.
- Stubs voor de volgende build-fasen: `app/services/ai_profile.py` (PROFILE_SCHEMA,
  `DraftProfile` dataclass, `_to_draft`-guard, Anthropic twee-staps signatures) en
  `app/routers/ai_profile.py` (lege `APIRouter`, gewired in `app/main.py`); Pydantic-schemas
  in `app/schemas/ai_profile.py` (`ChatMessageForm`, `AcceptForm`, `DraftProfileOut`).

## [0.6.1] - 2026-06-18
### Docs
- `docs/PRD-ai-profiel.md`: PRD voor AI-native profielbouw — gesprek met Claude Opus 4.8
  (`web_fetch`/`web_search` + structured outputs) dat links ophaalt/verrijkt incl. echte beelden,
  plus fal.ai-cover. Datamodel, edge cases, fasering. APPROVAL PENDING.

## [0.6.0] - 2026-06-17
### Added
- `CloudflareEmailSender` (`app/email/cloudflare_sender.py`): productie-e-mail via de
  Cloudflare Email Service REST-API (`/accounts/{id}/email/sending/send`), achter dezelfde
  `EmailSender`-interface. Selecteerbaar via `EMAIL_BACKEND=cloudflare`.
- Config: `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` (token-permissie "Email Sending: Edit").
- Tests: factory-selectie + failure-surfacing (non-2xx + netwerkfout) voor de Cloudflare-backend.
### Notes
- Activatie wacht op: Email Service per-account aanzetten (beta) + verzenddomein onboarden
  (SPF/DKIM) + de "Email Sending: Edit"-scope op het CF-token. Tot dan blijft `console` actief.

## [0.5.0] - 2026-06-17
### Added
- Teaser/coming-soon-pagina (`teaser/`): self-contained "kosmische diepte"-landing —
  canvas-constellatie (driftende sterren die verbindingslijnen vormen), nebula-mesh,
  Fraunces + JetBrains Mono + Spline Sans, roterende maker-rollen, e-mailwachtlijst.
- Minimale teaser-service (FastAPI + SQLite): serveert de pagina, `/healthz`, en
  `/api/waitlist` (e-mailvalidatie, idempotent via UNIQUE).
- Docker-compose (teaser + cloudflared) voor de M4.
### Deployed
- **Live op https://dewereldvan.ai** — self-host op M4 achter een eigen Cloudflare Tunnel
  `dewereldvan-teaser` (los van `n8n-tunnel`), ingress + DNS (apex + www) via de CF API.
### Decided
- E-mail definitief via **Cloudflare Email Service** (Workers Paid actief) i.p.v. Resend —
  één vendor voor DNS + tunnel + e-mail, laagste op-last. Zie context/decisions.md.

## [0.4.0] - 2026-06-17
### Security
- CSRF-bescherming op alle state-changing requests (`app/csrf.py`): per-sessie
  token in de signed cookie, gevalideerd op POST/PUT/PATCH/DELETE via een
  pure-ASGI middleware. Token in verborgen veld (HTML-forms) en als
  `X-CSRF-Token`-header (htmx, globaal via `hx-headers` op `<body>`).
  SameSite=Lax blijft als defense-in-depth.
- Session-cookie krijgt de `Secure`-flag (`https_only=True`) +
  `ProxyHeadersMiddleware` zodat de app het https-schema van de Cloudflare-tunnel
  vertrouwt op de interne http-hop.
- Open registratie per-IP rate-limited (`rate_limit_register_per_hour`, default
  5) tegen e-mail-bombing / ongebreidelde pending-rij-groei; nieuwe kolom
  `member.registration_ip`. Idempotente herhalingen en de admin-bootstrap-mail
  worden niet geteld.
- Magic-link single-use is nu concurrency-veilig: consumptie via atomische
  `UPDATE ... WHERE used_at IS NULL`; een gelijktijdige tweede verify krijgt
  `used` i.p.v. een tweede sessie.
### Added
- Eerste-admin-bootstrap: een geconfigureerd `ADMIN_EMAILS`-adres registreert
  direct als `approved` + `admin` (met audit-rij), zodat een verse deployment
  niet vastloopt zonder approver.
- AVG: expliciete instemming bij publiek zetten. `Profile.consented_public_at`
  legt het moment van toestemming vast; `change_visibility()` weigert de
  publieke transitie zonder consent (`ConsentRequired`) en het edit-formulier
  heeft een verplichte toestemmings-checkbox.
### Fixed
- Geschorste/geweigerde leden worden gedelist: een publiek profiel van een
  niet-approved eigenaar is niet langer wereld-leesbaar of indexeerbaar
  (`can_view`/`is_noindex` poorten op eigenaar-status).
- Admin htmx approve/reject/suspend op een verdwenen lid retourneert nu een
  inline `<tr>`-fragment i.p.v. de volledige 404-pagina (correcte htmx-swap).
- `ConsoleEmailSender` lekte een file-handle per verzending (outbox.log nu via
  context-manager).
### Changed
- `_naive_utc` (3× gedupliceerd in services) geconsolideerd naar
  `app.security.naive_utc`.
- Profiel-offerings/needs toevoegen/verwijderen via relatie-collectie
  (idiomatisch SQLAlchemy 2.x) i.p.v. `db.refresh` + dubbele flush.
- Dode alias `require_approved` verwijderd (`require_member` was de enige
  gebruiker).

## [0.3.0] - 2026-06-17
### Added
- Fase 1 profielen-MVP (FEATURES): volledige flows op de Fase-0-fundering.
- Auth (`app/routers/auth.py`): open registratie (idempotent op dubbele e-mail),
  passwordless magic-link aanvraag/verificatie (eenmalig, gehasht, TTL),
  uitloggen. Admin-notificatie-e-mail bij nieuwe aanmelding.
- Profielen (`app/routers/profiles.py`): profiel bewerken (bio, "wat ik maak",
  "waar ik naar zoek", tags), completeness-indicator, zichtbaarheid per profiel
  (alleen-leden default / openbaar), publieke slug-pagina (indexeerbaar) vs.
  besloten (login-gated + `noindex`). htmx voor offering/need toevoegen+
  verwijderen en de zichtbaarheid-toggle.
- Admin (`app/routers/admin.py`): goedkeuringsqueue met één-klik goedkeuren/
  weigeren/schorsen (htmx row-swap) + audit_log.
- Services (`app/services/`): registration (idempotent + pending-expiry purge),
  magic_link (issue/verify, single-use, expiry, rate-limit), approval
  (state-machine + audit), profile_service (upsert, offerings/needs/tags,
  completeness-scoring), visibility (wijziging + audit + read-enforcement).
- Schemas (`app/schemas/`): Pydantic v2 forms voor registratie, login en profiel
  (e-mailvalidatie via regex — geen extra dependency).
### Fixed
- Tijdzone-mismatch tussen tz-aware `utcnow()` en de tz-naive timestamp-kolommen:
  service-laag normaliseert naar naive-UTC vóór opslag/vergelijking (zou ook op
  Postgres `TIMESTAMP WITHOUT TIME ZONE` falen).
### Edge cases afgedekt (PRD §4)
- Dubbele registratie idempotent; geen account-enumeratie bij login.
- Verlopen/hergebruikte/ongeldige magic-link → nette her-aanvraag (geen silent fail).
- E-mailverzending mislukt → zichtbare foutstatus (502), nooit stil.
- Zichtbaarheid openbaar→besloten → direct delisten + `noindex` op de read-path.
- Pending-account-expiry + `purge_expired_pending`; rate-limit op magic-link.
- AVG: audit_log bij goedkeuringen/weigeringen/schorsingen en zichtbaarheidswijziging.

## [0.2.0] - 2026-06-17
### Added
- Fase 0 fundering: FastAPI app-factory met SessionMiddleware (signed cookies),
  Jinja2-templates, static, `/healthz` (app + DB-ping), landing + 404/500 pagina's.
- SQLAlchemy 2.x getypeerde modellen (Mapped/mapped_column): member, magic_link_token,
  profile, tag + profile_tag (M2M), offering, need, audit_log. Enums als VARCHAR+CHECK
  (`native_enum=False`) voor identieke schema's op Postgres en SQLite.
- `app/security.py`: magic-link tokengeneratie/hashing/verificatie (raw token nooit
  opgeslagen) + slug-helpers.
- E-mail-abstractie (`app/email/`): EmailSender Protocol, ConsoleEmailSender (dev-outbox),
  ResendEmailSender (prod), backend-selectie via `EMAIL_BACKEND`.
- Config via pydantic-settings (`app/config.py`) + `.env.example`.
- Gedeelde deps (`app/deps.py`): current_member, require_member/require_approved,
  require_admin, email_sender.
- Lege router-stubs (auth/profiles/admin) gekoppeld in `main.py` voor de FEATURES-fase.
- Alembic baseline-migratie `0001_initial_fase1` met alle Fase-1 tabellen.
- Docker: Dockerfile (python:3.12-slim), docker-compose (web + postgres + cloudflared,
  healthchecks, restart: unless-stopped, pgdata-volume), `.dockerignore`.
- `requirements.txt` (gepinde 2026-versies), `pyproject.toml` (pytest + ruff).

## [0.1.0] - 2026-06-17
### Added
- Projectinitialisatie: git op `main`, CLAUDE.md (Groot scope), context-documentatie.
- Architectuur, beslissingen en tech-stack vastgelegd.
- PRD/roadmap (`docs/PRD.md`) met fasering Fase 0–5 en edge cases — APPROVAL PENDING.
- Kernbeslissingen: visie (directory+matchmaking+community+showcase), open registratie +
  goedkeuring + magic-link, zichtbaarheid per profiel, self-host M4 + Cloudflare Tunnel,
  stack FastAPI + SQLAlchemy + Jinja2/htmx + Postgres.
