# Project Status — single source of truth

> **Onderhoudsregel**: dit bestand + `decisions.md` worden bijgewerkt **samen met
> elke `VERSION`/`CHANGELOG`-bump** (uitbreiding van Gouden Regel #1). Het is de
> "waar staan we"-waarheid; raakt het achter, dan misleidt het. Houd het kort —
> details staan in `CHANGELOG.md`, de PRD's en de memory (zie pointers onderaan).

**Laatste update**: 2026-06-21 · **Versie**: 0.52.0 · **Branch**: `main`

## Waar het draait
- **Preview (volledige app)**: https://app.dewereldvan.ai — M4 (`server-mini`), Docker
  Compose (`web` FastAPI + `postgres` 16 + `cloudflared`), eigen tunnel `dewereldvan-app`.
  Redeploy = `rsync ./ → ~/dewereldvan-app/` (excl. `.env`/`data`/`.venv`/`teaser`) +
  `docker compose up -d --build web`; migraties draaien via Dockerfile-CMD. Details:
  memory `dewereldvan-deploy`.
- **Teaser (apex)**: https://dewereldvan.ai — losse wachtlijst-service, eigen tunnel
  `dewereldvan-teaser`. Bij echte launch: apex-ingress overzetten naar de app.
- AI/integraties live op preview: `ANTHROPIC_API_KEY`, `FAL_KEY`, `AI_ENRICH_ENABLED=true`,
  Cloudflare Browser Rendering (screenshots), **Telegram-bot** (@dewereldvanaibot).

## Wat er staat (live op preview)
- **Toegang**: open registratie → admin-goedkeuring → passwordless magic-link → server-side sessie.
- **Agent-Shell**: voor ingelogde leden ís de concierge de navigatie (geen menu); interfaces
  materialiseren in-stroom via de `surface`-tool (registry in `concierge_service`).
- **Profiel**: levende AI-profielbouw (`/profiel/ai/bouwen`), inline editen, fal-cover, AI-toolsets.
  **Bekijk-als-bezoeker** (`/profiel/voorbeeld`, v0.48.0): zie exact wat anderen zien vóór je publiceert —
  zelfde publieke `view.html` met `is_owner=False`, altijd `noindex`, progress-bewuste preview-chrome
  ("Maak openbaar" alleen als het nog niet openbaar is). Ingangen op bewerk-header + AI-publiceer-dok.
- **Projecten**: screenshot-hero + AI-samenvatting (Cloudflare Browser Rendering, async + nachtjob).
- **Community**: agenda + nieuws (`Post`), ideeënbus, roadmap.
- **Matchmaking**: `MatchSuggestion` + intro-flow (`Connection`) + push-chips.
- **Discovery** (footprint-engine): zoekt een lid online op → entity-resolution → classificeer →
  crystalliseer. Draait als **achtergrond-job** (`DiscoveryRun`), live-tail over SSE, terugkeer-view,
  in-app "klaar"-chip. Hoge confidence (≥90) crystalliseert auto met undo; twijfel = 1-klik bevestigrij.
  **Verdieping** (opt-in): na de brede pass biedt de agent een gerichte **media-pass** aan (`focus="media"`,
  append + dedup) die interviews/artikelen/vermeldingen óver het lid zoekt. Events = fast-follow.
  **Progress-bewust** (`DiscoveryRun.passes`, migr. 0021): de CTA + het verdiepings-aanbod passen zich aan op
  wat al liep — geen "verse" knop of reeds-gebruikt aanbod (principe: de interface begrijpt wat gebruikt is).
- **Notificaties**: **geen e-mail** (behalve magic-link) → lid-gekozen kanaal. In-app pull-chips +
  optioneel **Telegram-push** (rich: vette titel + actieknop). Instellingen op `/profiel/notificaties`
  (ook als concierge-surface). Modellen `member_channel` + `notification_pref`.
- **MCP-server**: `/mcp` (Bearer-token per lid) — "praat met dewereldvan vanuit je eigen AI-tool".
- **Ervaring/motion** (v0.49–0.50): reveals zijn niet langer één uniform trucje. Scroll-reveal
  (`IntersectionObserver`, opt-in `data-reveal-scroll`), semantische varianten (`materialize`/`drift`)
  en per-bezoek variatie (reveal-mood + constellatie-mood). **Volledig uitgerold** (v0.50.0) over homepage,
  ledengids, projecten, agenda, nieuws, ideeën, roadmap; director htmx-bewust (geswapte fragmenten
  her-geobserveerd). Statische assets cache-gebust (`?v={{ asset_ver }}`). Volledig reduced-motion-safe.

## Huidige focus
**Strategische richting bepaald** (2026-06-21, 4 visie-subteams → `docs/vision/`): De Wereld van AI = een
levende kaart van het scherpste AI-netwerk waar een agent vóór het lid de graaf doorwerkt; nieuws/tools zijn
ondergeschikt aan de graaf. Goedgekeurd: **kosten-fundament → Concept A** (bezoeker bouwt live een mini-kaart
uit één URL), met groen licht voor betaalde niet-lid-calls onder een **harde €50/week-cap**.
- **Fase 1 (fundament)** live (v0.51.0): `AiSpendLog` + `visitor_ai_guard` (harde €50/wk-cap) + metering +
  Turnstile-service + `client_ip`.
- **Fase 2 = Concept A** live (v0.52.0): `/proef` — niet-lid plakt URL → gecapte Opus-call → kosmische
  mini-kaart (WIE/THEMA/MATCH) → toegang-CTA. Admin-meter op `/admin/queue`. **Geactiveerd** met Turnstile-keys
  in de M4-`.env` (2026-06-21) → het pad is nu live binnen de €50/wk-cap.

## Open taken
- [x] **Telegram end-to-end gevalideerd in prod** (2026-06-20): koppelen → discovery-job (12 findings, ~3,5 min)
      → push met knop. Koppelen is nu opt-in (voorkeur auto op telegram, v0.45.0).
- [ ] **Discovery-precisie meten**: hoeveel van de 12 findings laat een lid staan vs. afwijzen? (drempel ≥90 ijken).
- [x] **Motion-uitrol** (v0.50.0): scroll-reveal + varianten op homepage, ledengids, projecten, agenda,
      nieuws, ideeën, roadmap; director her-observeert geswapte htmx-fragmenten (geen onzichtbare content).
- [x] **Zombie-run-vangnet** (v0.49.0): `sweep_orphaned_runs` veegt bij app-start (`_lifespan`) elke verweesde
      `running`-discovery-run → `failed`. Idempotent, best-effort. Geen handmatige pre-deploy-check meer nodig.
- [x] **Concept A (Fase 2)** (v0.52.0): `/proef` live áchter `visitor_ai_guard`; admin-meter + Telegram-ping.
- [x] **Turnstile-keys gezet** (2026-06-21): widget aangemaakt, keys in M4-`.env` → Concept A geactiveerd.
- [ ] **Turnstile secret roteren** vóór publieke launch (de keys zijn in chat gedeeld — zelfde voorzorg als de bot-token).
- [ ] **De Briefing** (nieuws) + **Tool-reviews** — operator-side, raken het €50-budget niet. Zie `docs/vision/02`, `03`.
- [ ] Browser-verificatie auto-crystallisatie-op-`load` (1b; JS, niet in TestClient te dekken).
- [ ] Bot-token **roteren** via @BotFather vóór publieke launch (token was in chat gedeeld).
- [ ] Bij launch: apex-ingress teaser→app + wachtlijst-adressen → `member`-tabel.
- [ ] CF API-token roteren / minimaal-scope runtime-token vóór publieke launch.

## Blokkades
- Geen harde blokkades.

## Pointers (waar staat de rest van de waarheid)
- **Recente historie + per-versie details**: `CHANGELOG.md` (canoniek, append-only).
- **Beslissingen (waarom)**: `context/decisions.md`.
- **Systeemkaart (routes, datamodel, env)**: `context/architecture.md`.
- **Per-feature PRD's**: `docs/PRD-*.md` (discovery, notificaties, scout, matchmaking, mcp, concierge, …).
- **Operationele/infra-kennis + valkuilen**: memory-dir (`MEMORY.md`-index → deploy, notificaties,
  ai-engine-constraints, toolsets, agent-shell, audit-roadmap).
