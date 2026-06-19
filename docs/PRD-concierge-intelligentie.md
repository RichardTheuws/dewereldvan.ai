# PRD — Concierge-intelligentie

**Status**: Fase 1+2+3 GELEVERD (v0.30.0–v0.32.0) · **Versie doc**: 1.1.0 · **Datum**: 2026-06-19
**Aanleiding**: platform-audit 2026-06-19 — "AI-native intelligentie & agent-shell → FAIL".
Zie `~/.claude/.../memory/dewereldvan-audit-roadmap.md` (Tier 2).

## Probleem

De concierge is de hele interface voor leden, maar gedraagt zich op drie punten nog
niet "superslim" (mandaat in CLAUDE.md):

1. **`explain` is een vaste 6-topic-woordenboek.** Elke vraag buiten die 6 onderwerpen
   geeft "Onbekend onderwerp" — een wow-killer voor een publiek dat dagelijks met AI
   bouwt. Elk nieuw onderwerp vereist nu een codewijziging.
2. **Geen gedistilleerd, sessie-overstijgend geheugen.** `concierge_turn` bewaart ruwe
   platte-tekst-turns (limit 20) en replayt die; er is geen compacte "wat ik over dit
   lid weet" die de agent altijd meekrijgt.
3. **Twee paradigma's náást elkaar.** De kosmische pagina's dragen nog het volledige
   `_cosmic_nav`-menu náást de canvas. Voor een ingelogd, goedgekeurd lid hoort er
   één shell te zijn (de canvas) — met de bestaande footer-fallback als a11y-vangnet.

## Niet-doelen

- Geen pgvector/embeddings nu (zelfde keuze als matchmaking: keyword-retrieval nu,
  embeddings = latere schaal-stap bij groei). Lage op-last weegt zwaarder dan recall-marge.
- Geen vrije generatie over platformfeiten: retrieval over een **gecureerde** corpus
  blijft de grounding-poort (de agent synthetiseert alleen uit teruggegeven snippets).
- Geen admin-CMS voor de kennisbank in Fase 1 (corpus leeft in code; later evt. DB).

## Fase 1 — `explain` → retrieval (RAG over gecureerde kennisbank)

**Grounding-redenering.** De concierge genereert al vrije prozá; de grounding zit erin
dat `explain` *gecureerde feiten* teruggeeft waaruit de agent put. We vergroten dus de
gecureerde corpus en maken 'm doorzoekbaar — geen versoepeling. Spiegelt het
match-service-patroon (goedkope kandidaten → gegronde synthese).

**Bouw.**
- `app/services/knowledge.py`: ~15 `KnowledgeEntry`'s (id, title, keywords, text) die de
  echte platformfeiten dekken (zichtbaarheid, AVG/wissen, magic-link login, registratie/
  goedkeuring, matchmaking, connect/intro, agenda, nieuws, MCP/verbind, profielbouw uit
  link, demo, preview/besloten, ideeën, roadmap, overzicht). `search(query, limit=3)` =
  deterministische keyword/token-score (geen LLM, geen dependency).
- `tool_explain(args)` neemt een **vrije `query`** (back-compat: `topic` wordt als query
  behandeld). Retourneert top-K gegronde snippets `{query, results:[{title,text}], count}`.
  0 hits → `{query, results:[], note}` (eerlijke fallback i.p.v. harde fout).
- `explain`-tool-schema: `query` (vrije tekst) i.p.v. de enum-`topic`.
- `SYSTEM_PROMPT`: explain is nu open — roep 'm aan met de vraag van het lid; beantwoord
  ALLEEN uit de teruggegeven snippets; niets gevonden → zeg dat eerlijk, verzin niets.
- `app/mcp_server.py::hoe_werkt_dewereldvan(vraag="")` gebruikt dezelfde KB (één bron).

**Edge cases.** Lege query → overzicht-entry. Tegenstrijdige/onbekende term → fallback.
Injectie in profieltekst → KB is read-only data, geen instructies (bestaande regel).

**Succescriterium.** Een vraag buiten de oude 6 onderwerpen ("kost dit geld?", "hoe log
ik in?", "wat gebeurt er met mijn data?") levert een gegrond antwoord uit de KB; een
echt onbekende vraag levert een eerlijke "dat weet ik niet". Tests groen incl. retrieval-
scoring, back-compat, fallback, grounding (geen verzonnen feiten).

## Fase 2 — sessie-overstijgend geheugen (gedistilleerd)

- `member_memory` (kolom op `Member` of 1:1-tabel): compacte, door de agent gedistilleerde
  "wat ik over dit lid weet" (≤ ~1500 tekens). Eén goedkope Claude-call ná een gesprek
  (gated op `AI_ENRICH_ENABLED`) merget saillante, door het lid zelf vertelde feiten.
- Injectie in `SYSTEM_PROMPT` per stream (naast de laatste turns).
- AVG: gewist in `delete_member_completely` + resetbaar; alleen lid-eigen context.
- Migratie + Postgres-pariteit-test (sa.false()/dialect-neutraal, projectconventie).

## Fase 3 — één shell

- `_cosmic_nav` conditioneel verbergen voor ingelogd + goedgekeurd lid (canvas = enige
  shell); anon/publiek + admin-`Beheer` houden nav. Footer-fallback blijft a11y-vangnet.
- Tests: nav afwezig voor lid, aanwezig voor anon; admin houdt Beheer; a11y-check.

## Volgorde & verantwoording

Fase 1 eerst: enige die "superslim" direct zichtbaar maakt voor elk lid, zit op de
MCP-activatiekoers, kleinst, volledig reversibel, geen nieuwe dependency. Fase 2 (datamodel
+ distill-call) en Fase 3 (a11y-gevoelig) erna, los verifieerbaar.
