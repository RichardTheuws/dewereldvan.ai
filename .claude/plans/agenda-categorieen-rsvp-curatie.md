# Plan — Agenda: categorieën + RSVP + AI-curatie (execution-ready)

> ✅ **VOLLEDIG UITGEVOERD + LIVE (2026-06-23)** — alle drie increments staan op productie:
> - Increment 1 (categorieën: badge + filterchips + AI-draft) — **v0.83.0**
> - Increment 2 (RSVP: aanwezig/organiseert/spreekt + graaf-knoop-namen) — **v0.84.0**
> - Increment 3 (AI-curatie via web-search, auto-keur ≥85 + datum + locatie → live; twijfel → `/admin/agenda`;
>   wekelijks maandag-cron) — **v0.85.0**. Bron-keuze: **web-search** (geen seed-lijst).
> Eerste supervised prod-run: 5 echte NL AI-conferenties gevonden, 3 auto-live, 2 pending. 1037 tests groen.
> De rest van dit bestand is de oorspronkelijke spec (referentie).


> **Doel van dit bestand**: het volgende increment zó vastleggen dat de volgende sessie
> **direct kan bouwen** (Gouden Regel #9), zonder opnieuw te verkennen. Aangemaakt aan het
> eind van de sessie van 2026-06-22 (v0.82.0). Alle paden/patronen hieronder zijn deze
> sessie geverifieerd.

## Context (waar we staan)
- Pivot compleet; platform live op `dewereldvan.ai`.
- Agenda + nieuws zijn **publiek leesbaar voor anon** (v0.81.0) en **bijdragen gaat via één
  slimme input** (link/tekst/voice → `post_draft_service` → concept-form) sinds v0.82.0.
- Richards richtkeuzes (bevestigd in chat 2026-06-22):
  1. **AI cureert én keurt zelf goed wat ze zeker kan keuren**; alleen twijfel → admin-queue.
  2. **Leden-input zo simpel mogelijk** — link / tekst / voice volstaat voor de draft. ✅ gedaan.
  3. Agenda in **categorieën**, met RSVP: **aanwezig / organiserend / ik spreek hier**.
- **Harde grondingsregel**: AI verzint NOOIT events (geen gehallucineerde datum/locatie).
  Elke auto-gevulde event komt uit een ECHTE URL (markdown-extractie), nooit uit model-geheugen.

## Increment 1 — Categorieën op events
- **Model**: `Post.category` (nieuwe `EventCategory`-enum in `app/models/base.py`):
  `meetup · conferentie · coding · workshop · talk · hackathon · overig` (default `meetup`).
  Additieve migratie (volgende = **0032**). `String(length=…)` of native_enum=False zoals
  `OfferingKind`/`EventFrequency` (zie `Offering.kind` als voorbeeld).
- **AI vult 'm bij de draft**: voeg `category` toe aan `post_draft_service._EVENT_TOOL`
  (enum) + map in `draft_event()`. Geen extra AI-call (zit in dezelfde tool-call).
- **Render**: categorie-badge op de event-kaart (`agenda/_card.html`, naast de frequentie-
  badge) + **filterchips** op `/agenda` (kopieer exact het discipline-chip-patroon:
  `members/_filters.html` + `.disc-chip` CSS + `:has(input:checked)`; server-filter in een
  `post_service.list_events(category=…)`-uitbreiding).
- **Tests**: draft mapt category; filter mapt op category; onbekend → genegeerd.

## Increment 2 — RSVP / aanwezigheid (de amaze: agenda wordt sociaal)
- **Model**: nieuw `EventAttendance` (`app/models/event_attendance.py`):
  `id, post_id (FK→post, CASCADE), member_id (FK→member, CASCADE), role (enum:
  attending|organizing|speaking), created_at`. Unieke constraint `(post_id, member_id)`
  (één rol per lid per event; her-zetten = update). Migratie **0033**.
  - Let op AVG: CASCADE op zowel post- als member-delete (spiegel `profile_tool`/account_deletion;
    check `app/services/account_deletion.py` — voeg attendance toe aan de wis-keten).
- **Service** `attendance_service.py`: `set_role(db, member, post, role)` (upsert),
  `clear(db, member, post)`, `for_event(db, post) -> {attending:[], organizing:[], speaking:[]}`
  (eager-load member→profile voor naam/slug), `counts(posts)` (in-memory, nul N+1).
- **Routes** (in `posts.py`, `require_member` + CSRF via body-`hx-headers`):
  `POST /agenda/{post_id}/rsvp` (form: `role`) → htmx-swap de RSVP-strip van die kaart;
  `POST /agenda/{post_id}/rsvp/clear`. Anon ziet de telling + "Word lid om je aan te melden".
- **Render**: op `agenda/_card.html` een RSVP-strip: drie knoppen (Aanwezig / Organiseert /
  Spreekt) met `:checked`-stijl voor de eigen keuze + gezichten/namen van wie gaat
  ("3 aanwezig · spreker: [[Naam]]"). Sprekers/organisatoren linken naar hun profiel →
  **graaf-knoop** (hergebruik de `related`/graph-gedachte; geen nieuwe graaf-tabel).
- **Tests**: upsert (rol wijzigen = geen dubbele rij), counts, anon kan niet RSVP'en
  (login-gate), account-deletion wist attendance.

## Increment 3 — AI-agenda-curatie (vult de agenda met ECHTE events; auto-keurt het zekere)
- **Spiegel exact het bestaande nieuws-curatie-patroon** (al gebouwd, werkt):
  - `news_curation_service.curate_news` (wekelijks/zondag) → admin-shortlist → `approve_news`.
  - admin-route `/admin/nieuws` (zie `posts.py` + `app/templates/nieuws/_briefing.html`).
  - `create_curated_news` zet items op **pending** tot goedkeuring.
- **Voor events**: nieuw `event_curation_service.py`:
  1. **Bron = echte URLs.** Begin met een lijst bekende NL/BE AI-communities (Aimelo, …) —
     Richard levert/bevestigt de seed-URLs, óf web-search (Brave/Tavily MCP) naar event-pagina's.
     **Nooit** events uit model-geheugen genereren.
  2. Per URL: `browser_render_service.markdown(url)` → `post_draft_service.draft_event`-achtige
     extractie (titel/datum/locatie/categorie/frequentie), mét een **confidence**-oordeel.
  3. **Auto-keuren wat zeker is** (spiegel `triage_service`: hoge confidence + geldige
     datum+locatie → direct live; twijfel → pending in admin-queue mét reden). KILL-fallback:
     `AI_ENRICH_ENABLED` uit of fout → alles naar pending (nooit auto-publish bij twijfel).
  4. **Dedup** op URL (idempotent — zoals discovery/crystalliseer): geen dubbele events.
  5. Admin-seintje bij pending via **`notify_admins`** (Telegram, v0.73.0) — niet e-mail.
- **Cron**: voeg toe aan de nachtelijke LaunchAgent-keten `scripts/nightly-jobs.sh` (M4,
  03:30) naast `refresh_matches`/`enrich_projects`. Wekelijks (bv. maandag) i.p.v. dagelijks.
- **Tests**: hoge-confidence→live, lage→pending, AI-uit→pending, dedup op URL, geen-datum→pending.

## Herbruikbare patronen/paden (deze sessie geverifieerd — NIET opnieuw zoeken)
- **Enums**: `app/models/base.py` (`OfferingKind`, `EventFrequency`, `NewsRole`).
- **List/JSON-kolom op Postgres**: gebruik `app/models/types.py` `JSON_LIST` (jsonb op PG —
  anders breekt `SELECT DISTINCT`; zie v0.80.1-fix). Draai `./scripts/test-postgres.sh` als je
  een list/json-kolom toevoegt aan een tabel die ge-DISTINCT't wordt.
- **Migraties**: `alembic/versions/` (laatste = `0031_json_to_jsonb`). Additief, dialect-neutraal,
  `down_revision` correct ketenen. Migratie draait auto bij deploy (Dockerfile-CMD).
- **Smart-input/draft**: `app/services/post_draft_service.py` + `app/templates/posts/_smart_add.html`.
- **AI-tool-call-patroon (Haiku, forced tool-use, fail-safe)**: `project_enrich_service.classify_work_item`
  + `triage_service` + `post_draft_service`. Altijd `settings.ai_enrich_enabled`-gated, `_tool_input`-helper.
- **Chip-filter**: `members/_filters.html` + `members_service.list_public_profiles` (discipline/open_to) +
  `.disc-chip`/`:has(input:checked)` in `cosmic.css`.
- **Curatie-mens-in-de-lus**: `news_curation_service` + `/admin/nieuws` + `_briefing.html`.
- **Admin-notificatie**: `notification_service.notify_admins` (Telegram).
- **UAT-contract**: nieuwe publieke GET-route? → zet 'm in `tests/test_uat_coverage.py`
  (`PUBLIC_INDEXABLE`/`MEMBER_ONLY`/…), anders faalt de zelf-groeiende UAT.
- **Browser-verificatie van member-flows lokaal**: seed approved member → uvicorn (console-mail)
  → login via outbox-magic-link **in de browser** (sessie-gebonden token; curl-token werkt niet
  in de browser). Of verifieer de server-flow met een ingelogde curl-cookie-jar.

## Werkvolgorde (aanbevolen)
1. Increment 1 (categorieën) — klein, gegrond, levert meteen filterbare structuur.
2. Increment 2 (RSVP) — de sociale amaze; onafhankelijk van bron.
3. Increment 3 (AI-curatie) — hangt af van de **bron-seed** (vraag Richard om de Aimelo-c.s.-lijst
   óf bevestig web-search). Bouw het curatie-mechanisme grond-first; vul daarna.

## Open vraag voor de bron (increment 3)
Richard koos "AI cureert + auto-keurt het zekere". Te bevestigen bij de start van increment 3:
de **concrete bron-seed** — levert Richard een lijst NL/BE AI-communities/events, of mag de
agent via web-search echte event-pagina's zoeken (elk gegrond + geverifieerd vóór publicatie)?
