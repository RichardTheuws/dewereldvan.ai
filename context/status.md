# Project Status — single source of truth

> **Onderhoudsregel**: dit bestand + `decisions.md` worden bijgewerkt **samen met
> elke `VERSION`/`CHANGELOG`-bump** (uitbreiding van Gouden Regel #1). Het is de
> "waar staan we"-waarheid; raakt het achter, dan misleidt het. Houd het kort —
> details staan in `CHANGELOG.md`, de PRD's en de memory (zie pointers onderaan).

**Laatste update**: 2026-06-21 · **Versie**: 0.49.0 · **Branch**: `main`

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
- **Ervaring/motion** (v0.49.0): reveals zijn niet langer één uniform trucje. Scroll-reveal
  (`IntersectionObserver`, opt-in `data-reveal-scroll`), semantische varianten (`materialize`/`drift`)
  en per-bezoek variatie (reveal-mood + constellatie-mood). Bewezen op `profiles/view.html`; uitrol
  naar leden-grid/projecten/community is fast-follow. Volledig reduced-motion-safe.

## Huidige focus
Net afgerond: notificatie-pivot (e-mail eruit, Telegram + avatar + rich content) en de
source-of-truth-opschoning (dit document). De engine + integraties staan; de nadruk verschuift naar
**ervaring polijsten + de keten live valideren** (Discovery-precisie meten, Telegram end-to-end testen).

## Open taken
- [x] **Telegram end-to-end gevalideerd in prod** (2026-06-20): koppelen → discovery-job (12 findings, ~3,5 min)
      → push met knop. Koppelen is nu opt-in (voorkeur auto op telegram, v0.45.0).
- [ ] **Discovery-precisie meten**: hoeveel van de 12 findings laat een lid staan vs. afwijzen? (drempel ≥90 ijken).
- [ ] **Motion-uitrol** (na v0.49.0): scroll-reveal + varianten doortrekken naar leden-grid, projecten en
      community (agenda/nieuws/ideeën/roadmap). Let op htmx-swap-pagina's: alleen read-only secties `data-reveal-scroll` geven.
- [x] **Zombie-run-vangnet** (v0.49.0): `sweep_orphaned_runs` veegt bij app-start (`_lifespan`) elke verweesde
      `running`-discovery-run → `failed`. Idempotent, best-effort. Geen handmatige pre-deploy-check meer nodig.
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
