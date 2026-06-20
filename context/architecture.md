# Architectuur — canonieke systeemkaart

> Bijwerken bij structurele wijzigingen (nieuwe router/model/integratie/migratie).
> Voor "waar staan we" zie `status.md`; voor "waarom" zie `decisions.md`.

## Systeem Overzicht
Eén self-hosted, server-rendered webapplicatie achter een Cloudflare Tunnel. Geen
SPA/JS-buildpipeline — interactiviteit via **htmx** (+ SSE voor live-streams). Lage
operationele last, draait unattended (kerneis).

```
Bezoeker ──HTTPS──► Cloudflare (DNS + WAF + Tunnel edge)
                          │  (cloudflared, geen open poorten)
                          ▼
                 ┌─────────────────────────────┐
                 │  Mac mini M4 (server-mini)   │
                 │  Docker Compose              │
                 │  ┌────────┐   ┌────────────┐ │
                 │  │ web    │──►│ postgres 16│ │
                 │  │FastAPI │   │ (volume)   │ │
                 │  └───┬────┘   └────────────┘ │
                 │      │  cloudflared (sidecar) │
                 └──────┼──────────────────────┘
        ┌──────────────┼───────────────┬───────────────┐
        ▼              ▼                ▼               ▼
   Anthropic      Cloudflare        fal.ai         Telegram Bot API
  (web_search,   Browser Render   (cover-art)     (push-notificaties)
   profielbouw,  (screenshots)
   concierge,
   discovery)
```
Twee tunnels/ingressen: **app.dewereldvan.ai** (volledige app) en **dewereldvan.ai**
(teaser). MCP-server gemount op `/mcp` (eigen Bearer-auth).

## Componenten (`app/`)
- **routers/** (20): HTTP-endpoints (zie route-inventaris). **services/**: de logica
  (engine-loops, persistentie, integraties). **models/**: SQLAlchemy 2.x (25 tabellen).
  **templates/**: Jinja2 + htmx-partials. **email/**: EmailSender-adapters (alleen nog
  magic-link). **mcp_server.py**: FastMCP op `/mcp`.
- **Sleutel-services**: `profile_service`, `concierge_service` (agent-shell function-tool-loop +
  `surface`-registry), `footprint_service` (discovery-engine), `discovery_job_service`
  (achtergrond-job), `notification_service` + `telegram_service`, `project_enrich_service`,
  `match_service`/`connection_service`, `nudge_service` (pull-chips), `cover_art_service`,
  `tool_service`, `member_memory_service`, `account_deletion`.

## Route-inventaris (gegroepeerd)
- **Auth/toegang**: `/register`, `/login`, `/auth/verify`, `/logout`, `/welkom`,
  `/uitnodiging/{token}`.
- **Profiel (AI-bouw)**: `/profiel/ai/bouwen`, `/profiel/ai/bericht|stream|opnieuw|publiceren|cover`,
  `/profiel/ai/offering|rol|veld/*` (CRUD/inline), `/profiel/ai/maak-draft`.
- **Profiel (klassiek + AVG)**: `/profiel/bewerken`, `/profiel/zichtbaarheid`, `/profiel/emphasis`,
  `/profiel/foto*`, `/profiel/need|offering*`, `/profiel/verwijderen`, `/profiel/gewist`.
- **Discovery**: `/profiel/ai/ontdek` (start/hervat/resume), `/ontdek/stream` (SSE-tail),
  `/ontdek/resultaat` (deeplink), `/ontdek/koppel|crystalliseer|ongedaan`.
- **Notificaties**: `/profiel/notificaties` (+ `/kanaal`, `/telegram/start|ontkoppel`),
  `/telegram/webhook` (extern, secret-header, CSRF-exempt).
- **Concierge/agent-shell**: `/concierge/bericht|stream|chips|index|nudge|profielbouw|founder/verhaal`.
- **Community**: `/leden`, `/leden/{slug}`, `/projecten/{slug}`, `/agenda`, `/nieuws`, `/ideeen`,
  `/roadmap`, `/intro/*`, `/feedback*`.
- **MCP/koppelen**: `/mcp`, `/profiel/verbind` (+ token-CRUD).
- **Admin**: `/queue`, `/members/{id}/approve|reject|suspend`, `/admin/*` (roadmap, ideeën,
  posts, feedback, uitnodiging).
- **SEO**: `/robots.txt`, `/sitemap.xml`.

## Datamodel (25 tabellen, migraties 0001–0020)
- **Kern**: `member`, `magic_link_token`, `profile`, `profile_link`, `tag`+`profile_tag`,
  `tool`+`profile_tool`, `offering`+`offering_slug_history`, `need`.
- **Community**: `post` (agenda+nieuws), `idea`+`idea_vote`, `roadmap_item`, `feedback`,
  `group_invite`.
- **Matchmaking**: `match_suggestion`, `connection`.
- **Agent/AI**: `concierge_turn`, `concierge_nudge_dismissal`, `ai_chat_turn` (het
  gedistilleerde concierge-geheugen leeft als `member.member_memory`-kolom, migr. 0015).
- **Discovery**: `discovery_run` (0019).
- **Notificaties**: `member_channel` + `notification_pref` (0020).
- **Auth/MCP/audit**: `personal_token` (MCP Bearer), `audit_log`.
- **AVG**: alle member-gebonden rijen worden expliciet gewist in `account_deletion`
  (test-bewijsbaar, niet op DB-cascade leunend).

## Env-vars (gegate integraties; zie `.env.example`)
`SECRET_KEY` (verplicht), `DATABASE_URL`, `BASE_URL`, `ADMIN_EMAILS`, `EMAIL_BACKEND`
(+ Cloudflare/Resend-creds — alleen magic-link), `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL`,
`FAL_KEY`, `AI_ENRICH_ENABLED`, `CLOUDFLARE_ACCOUNT_ID`/`_API_TOKEN` (Browser Rendering),
`MCP_BASE_URL`, `TELEGRAM_BOT_TOKEN`/`_BOT_USERNAME`/`_WEBHOOK_SECRET`, diverse
`RATE_LIMIT_*`. Ontbrekende creds → de feature is een nette no-op (geen crash).

## Fasering — status
- **Fase 0–1 (fundering + toegang + profiel)** — ✅ live.
- **Fase 2 (directory + AVG + agent-shell schrijf-surfaces)** — ✅ live.
- **Fase 3 (matchmaking)** — ✅ live (suggesties + intro-flow + push-chips).
- **Community (agenda/nieuws/ideeën/roadmap)** — ✅ live.
- **MCP-server** — ✅ live.
- **Discovery (footprint-engine + achtergrond-job + crystalliseer)** — ✅ live; Scout (Fase 2) volgt.
- **Notificaties (lid-gekozen kanaal + Telegram)** — ✅ live; per-event-voorkeuren later.

## Operationele eisen (unattended)
- Nightly Postgres-backup + nachtelijke jobs (`refresh_matches`, `distill_memories`,
  `enrich_projects`) via LaunchAgent op de M4.
- Healthcheck `/healthz` + container `restart`-policy; migraties bij startup (Dockerfile-CMD).
- Enige handmatige stap in normale werking: de lichtgewicht goedkeurings-queue.
