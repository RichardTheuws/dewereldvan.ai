# Project Status — single source of truth

> **Onderhoudsregel**: dit bestand + `decisions.md` worden bijgewerkt **samen met
> elke `VERSION`/`CHANGELOG`-bump** (uitbreiding van Gouden Regel #1). Het is de
> "waar staan we"-waarheid; raakt het achter, dan misleidt het. Houd het kort —
> details staan in `CHANGELOG.md`, de PRD's en de memory (zie pointers onderaan).

**Laatste update**: 2026-06-22 · **Versie**: 0.81.0 · **Branch**: `main`

## Waar het draait
- **🚀 LIVE (volledige app)**: **https://dewereldvan.ai** (apex, canonical) + `www` + `app.dewereldvan.ai` —
  alle drie via de `dewereldvan-app`-tunnel naar dezelfde app. M4 (`server-mini`), Docker Compose
  (`web` FastAPI + `postgres` 16 + `cloudflared`). `BASE_URL=https://dewereldvan.ai`. Redeploy =
  `rsync ./ → ~/dewereldvan-app/` (excl. `.env`/`data`/`.venv`/`teaser`) + `docker compose up -d --build web`;
  migraties draaien via Dockerfile-CMD. Details: memory `dewereldvan-deploy`.
- **Teaser**: buiten dienst sinds de launch (2026-06-22, v0.79.1); stack gestopt, wachtlijst-volume bewaard.
- AI/integraties live op preview: `ANTHROPIC_API_KEY`, `FAL_KEY`, `AI_ENRICH_ENABLED=true`,
  Cloudflare Browser Rendering (screenshots), **Telegram-bot** (@dewereldvanaibot).

## Wat er staat (live op preview)
- **Toegang**: open registratie → admin-goedkeuring → passwordless magic-link → server-side sessie.
  Goedkeuren stuurt zélf de welkomst-/login-mail (v0.69.0, fail-safe in `approve_member`) — geen handmatig porren.
- **Agent-Shell**: voor ingelogde leden ís de concierge de navigatie (geen menu); interfaces
  materialiseren in-stroom via de `surface`-tool (registry in `concierge_service`). De canvas-ruststaat
  toont de levende makers-graaf (v0.68.0) en is **tijd-bewust** (v0.70.0): pas-verschenen makers gloeien +
  de kop erkent "{K} nieuw deze week" (`members_service.select_living_stars`, nul AI).
- **Profiel**: levende AI-profielbouw (`/profiel/ai/bouwen`), inline editen, fal-cover, AI-toolsets.
  **Bekijk-als-bezoeker** (`/profiel/voorbeeld`, v0.48.0): zie exact wat anderen zien vóór je publiceert —
  zelfde publieke `view.html` met `is_owner=False`, altijd `noindex`, progress-bewuste preview-chrome
  ("Maak openbaar" alleen als het nog niet openbaar is). Ingangen op bewerk-header + AI-publiceer-dok.
- **Projecten**: screenshot-hero + AI-samenvatting (Cloudflare Browser Rendering, async + nachtjob).
- **Open voor** (v0.80.0): elk profiel kan engagement-beschikbaarheid kiezen (klantwerk/trainingen/spreken/
  interviews/samenwerkingen → `Profile.open_to` JSON, `openness_service`). Publiek = gloeiende **beacons** die
  voor een bezoeker actionable zijn (klik → concierge-prefill met intro, nul AI-kosten); editor toont een
  gegronde suggestie uit de werk-items; `/leden` heeft een "Open voor"-discovery-filter.
- **Community**: agenda + nieuws (`Post`), ideeënbus, roadmap. **Agenda + nieuws zijn publiek leesbaar voor
  anon** (v0.81.0, indexeerbaar; toevoegen blijft login-gated → "Word lid"-nudge).
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
  (ook als concierge-surface). Modellen `member_channel` + `notification_pref`. **Admin-communicatie loopt
  via Telegram** (v0.73.0, `notify_admins` — directe push naar admin-Telegram, niet e-mail): nieuwe-aanmelding
  + nieuws-shortlist. Vereist dat Richard z'n Telegram koppelt.
- **MCP-server**: `/mcp` (Bearer-token per lid) — "praat met dewereldvan vanuit je eigen AI-tool".
- **Ervaring/motion** (v0.49–0.50): reveals zijn niet langer één uniform trucje. Scroll-reveal
  (`IntersectionObserver`, opt-in `data-reveal-scroll`), semantische varianten (`materialize`/`drift`)
  en per-bezoek variatie (reveal-mood + constellatie-mood). **Volledig uitgerold** (v0.50.0) over homepage,
  ledengids, projecten, agenda, nieuws, ideeën, roadmap; director htmx-bewust (geswapte fragmenten
  her-geobserveerd). Statische assets cache-gebust (`?v={{ asset_ver }}`). Volledig reduced-motion-safe.

## Huidige focus
**🔭 PIVOT (2026-06-22) — open multidisciplinair maker-platform met showcase.** Strategische koers-
wijziging: van besloten WhatsApp-groep → **open voor iedereen met AI-affiniteit, alle disciplines**.
De poort **filtert spam, niet mensen** (AI-spam-triage → auto-welkom voor echte makers, alleen twijfel
in de review-queue; nooit "niet geschikt"). Het profiel wordt een agent-gebouwde **multidisciplinaire
showcase** (project/workshop/video-showreel/audio/galerij via een typed werk-item-model = generalisatie
van `Offering`). **PRD: `docs/PRD-open-showcase.md` (v0.1.0, APPROVAL PENDING)** + beslissing 2026-06-22
in `decisions.md`. Fasering A (toegang herframen) → B (spam-triage + auto-welkom) → C (showcase) → D
(discipline-facet). **Fase A+B LIVE**: A (v0.71.0) herframede registratie/queue/mail (poort = anti-spam,
niet oordeel). B (v0.72.0): de open preview-banner + **spam-triage** (`triage_service`, Haiku) bij
registratie → **auto-welkom** voor echte makers, alleen twijfel in de queue (mét reden); nooit auto-weren;
KILL-fallback naar review bij AI-uit/fout (migr. 0026 `member.triage_note`). **Fase C increment 1 LIVE**
(v0.74.0): `Offering.kind` + `embed_html` (migr. 0027); `embed_service` maakt video/audio-showreels uit een
link (oEmbed, provider-allowlist, SSRF/XSS-veilig, fail-safe → link). **Inc.2 LIVE** (v0.75.0): workshop —
één Haiku-tool-call (`classify_work_item`) classificeert
een link als event→workshop (datum/locatie, migr. 0028), article→writing (v0.76.0), of other→project; render
past zich aan per kind. **Fase D LIVE** (v0.77.0): discipline-filter op /leden (Bouwers/Video-AI/Audio-AI/
Trainers/Publicaties) afgeleid uit `offering.kind` (geen apart datamodel) + per-kaart discipline-tags.
**Discovery-op-discipline LIVE** (v0.78.0): de match-engine is werk-soort-bewust — een `Need` die expliciet
om een workshop/video/audio/publicatie vraagt haalt werk-items van dát soort naar voren (zero-AI
`infer_desired_kinds` → `DISCIPLINE_BOOST` in de kandidaat-ranking; werk-soort meegegeven aan het LLM-oordeel).
Zo voedt de Fase-D-data nu matchmaking, niet alleen de gids-filter. **Galerij-werk-item LIVE** (v0.79.0,
Fase C inc.4 — de laatste pivot-bouwsteen): de agent herkent een portfolio-link → `kind=gallery`,
`extract_gallery_images` hotlinkt de beeld-URLs uit de Cloudflare-markdown (nul-opslag, geen SSRF), render =
beeld-raster + 🖼-badge; fail-safe < 2 beelden → blijft project. Discipline **Design** toegevoegd aan
gids-filter + match. Migratie 0029 (`offering.gallery_urls` JSON). **De pivot (A→D + showcase incrementen 1-4)
is daarmee compleet.** NB admin-comms via Telegram (v0.73.0, `notify_admins`).

### Eerdere focus (afgerond)
**Sitewide ervaring-audit + UAT-fundament** (2026-06-21, v0.56.0). Een read-only audit-workflow toetste 12
schermen tegen de noordster (W1–W5) + STYLEGUIDE: **9/10 FAIL, alleen de besloten canvas PASS** — patroon is
overal "mooi maar niet slim" (kosmische schil grotendeels conform, maar het W-mechanisme + getoonde
intelligentie/gegrondheid ontbreekt). Veel intelligentie is **al gebouwd maar wordt niet getoond/weggegooid**,
dus de meeste hoogste-leverage-ingrepen zijn "maak zichtbaar", niet "bouw". Geprioriteerd bouwplan:
- **Blok 0 (klaar, v0.56.0)** — Slimme, zelf-groeiende **UAT**: Laag 1 (route-dekkingswacht, geen-5xx +
  auth-poorten + volledigheids-gate) + Laag 2 (ervaring-invarianten: cosmic-identiteit + fonts + noindex-poort).
  Laag 3 (browser-journeys, `e2e`-marker) voorbereid; bouwen ná het homepage-kopstuk.
- **Blok 1 (klaar, v0.57.0)** — **Homepage-kopstuk** = Concept B-hybride: embedded agent-demo (W2, gedeelde
  `_home_demo.html` + `static/demo-play.js`, ook door `/demo` gebruikt), echte makers-constellatie met gegronde
  tag/tool-lijnen (W1, `compute_graph_links`), proef-chips via veilige `data-concierge-prefill`-haak (anon =
  gratis instant-matches; betaalde stream UI-geblokkeerd voor anon), prominente `/proef`-CTA. Adversarieel
  geverifieerd; 904 tests groen.
- **Anon-budget-poort (klaar, v0.57.1)** — `/concierge/stream` is leden-only voor de betaalde agent; anon krijgt
  gratis ontdek-laag + "word lid" (server-side garantie naast de UI-blokkade). Sluit de enige ongecapte betaalde
  niet-lid-route → €50/wk-cap beschermd. 905 tests groen.
- **Resterende follow-up**: Tailwind dev-CDN → vooraf-gebouwde CSS op publieke pagina's (FOUC-risico mobiel,
  pre-existing, eigen blokje).
- **Blok 2 (compleet)** — `/proef` ✅ (v0.58.0) · publiek profiel = graaf-knoop ✅ (v0.59.0) · `/leden` verbonden
  graaf ✅ (v0.60.0) · `/demo` scan→veld-causaliteit ✅ (v0.61.0). **Uitgesteld**: volledige interactieve
  force-graph op `/leden` (L-effort; eigen blok).
- **Blok 3 (compleet)** — project ✅ (v0.62.0) · nieuws ✅ (v0.62.1) · roadmap ✅ (v0.63.0) · agenda + 6
  contextuele concierge-prompts ✅ (v0.63.1) · ideeën near-duplicate-hint ✅ (v0.64.0) · auth agent-aan-de-deur
  ✅ (v0.65.0: gescripte demo op invite-landing, nul AI-kosten).
- **Hele audit-plan af** (Blok 0→3) + **Tailwind-CDN→util.css** ✅ (v0.66.0) + **dode code opgeruimd** ✅
  (v0.66.1) + **Browser-UAT (Laag 3) compleet + gedraaid + visueel geverifieerd** ✅ (v0.67.0: `tests/e2e/`,
  Playwright/Chromium tegen echte app, geseede SQLite, AI uit; 6 journeys + harde JS-error-vangst; nacht-CI-job;
  `pip install -r requirements-e2e.txt && playwright install chromium && pytest -m e2e tests/e2e/`).
- **Lid-canvas ambient graaf** ✅ (v0.68.0): de canvas landt niet meer leeg — de echte levende constellatie ("De
  wereld nu") óók voor leden, gegrond/nul-AI, browser-geverifieerd als ingelogd lid. **Inzicht**: een lid ziet
  de canvas (dual-shell), niet de publieke kopstuk-voordeur — dat moet apart verrassen.
- **Volgende (lid-canvas verras-slices)**: gegronde "sinds je weg was"-signalen (nieuwe makers deze week,
  openstaande matches/intro's via `match_service`/`connections`) in de ambient ruststaat.
- **Resterend eigen blok**: volledige interactieve `/leden`-force-graph (L-effort). **Werkregel**: nooit "af"
  zonder eigen browser-verificatie — zie memory `feedback-verify-before-done`.
- **Blok 3** — project, nieuws, agenda, ideeën, roadmap, auth.
- **Niet doen**: geen tweede look; geen LLM voor graaf-relaties (strict uit DB → nul kosten/hallucinatie); geen
  vrij betaald agent-veld op de publieke voordeur; geen nieuwe e-mailkanalen.

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
- [x] **De Briefing** (nieuws, v0.53.0–0.53.1): AI-curatie (`curate_news`, wekelijks/zondag) → mens-in-de-lus
      admin-shortlist → kosmische briefing-strip. Eerste prod-run geobserveerd (3 rake kandidaten, 1 bug gevangen+gefixt); kandidaten goedgekeurd.
- [x] **Tool-reviews** (`docs/vision/03`): Fase A+B (v0.54.0, AI-dossier geen sterren, ≥1-gebruiker-drempel,
      SSRF-guard, oude-review-behoud) + Fase C (v0.55.0, mens-naast-AI-correctie-notes, admin-verberg + admin-only
      "ververs nu"). Live geverifieerd: 3 echte dossiers (Claude Code/Cursor/Obsidian). Fase D (netwerk-grounding-filter) = fast-follow.
- [ ] Browser-verificatie auto-crystallisatie-op-`load` (1b; JS, niet in TestClient te dekken).
- [x] **🚀 Launch** (2026-06-22, v0.79.1): apex+www-ingress teaser→app (CF-API), DNS omgezet, `BASE_URL`→apex,
      wachtlijst (6) → `member` (4 al lid, 2 nieuw pending), teaser gestopt. Browser-geverifieerd.
- [x] **Homepage-copy pivot-conform** (v0.79.2): hero-subkop + SEO-desc "besloten"→"open" (sluit op de banner aan).
- [ ] **Optioneel**: `www`→apex 301-redirect (nu serveren beide; canonical wijst al naar apex).

## Blokkades
- Geen harde blokkades.

## Pointers (waar staat de rest van de waarheid)
- **Recente historie + per-versie details**: `CHANGELOG.md` (canoniek, append-only).
- **Beslissingen (waarom)**: `context/decisions.md`.
- **Systeemkaart (routes, datamodel, env)**: `context/architecture.md`.
- **Per-feature PRD's**: `docs/PRD-*.md` (discovery, notificaties, scout, matchmaking, mcp, concierge, …).
- **Operationele/infra-kennis + valkuilen**: memory-dir (`MEMORY.md`-index → deploy, notificaties,
  ai-engine-constraints, toolsets, agent-shell, audit-roadmap).
