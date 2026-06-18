# PRD — AI-native profielbouw

**Versie**: 0.1.0 · **Datum**: 2026-06-18 · **Status**: 🟡 APPROVAL PENDING

## 1. Doel
Leden bouwen hun profiel via een **gesprek met de AI**: ze vertellen in gewone taal wie ze
zijn en plakken hun links; het systeem haalt die links op, verrijkt ze (info + echte beelden)
en bouwt een rijk, kloppend profiel — dat het lid daarna verfijnt en publiceert. De flow moet
uitmuntend en zichtbaar slim zijn (doelgroep = de scherpste AI-mensen van NL/BE).

**Voorbeeld-input (Richard):** "Ik ben Richard Theuws, profiel op theuws.com, verantwoordelijk
voor een groot deel van de digitale zaken van metalbc.com, ik bouw ondernemenindekempen.nl,
reign-of-brabant.nl en elementals.nl." → rijk profiel met per link omschrijving + beeld.

## 2. Techniek (vastgelegd)
- **Model**: Claude **Opus 4.8** (`claude-opus-4-8`), adaptive thinking, streaming.
- **Tools (server-side)**: `web_fetch_20260209` + `web_search_20260209` — Claude haalt de links
  zelf op (met dynamische filtering), leest ze en extraheert info + afbeeldings-URL's
  (og:image, logo, screenshot). Geen eigen scraper.
- **Structured outputs** (`output_config.format`) → gegarandeerd profielschema.
- **Beeldgeneratie**: **fal.ai** voor een cover/sfeerbeeld, achter een kleine `ImageGenerator`-
  interface (zelfde patroon als `EmailSender`, provider-swappable).
- **Kosten**: ~€0,20–0,40 per profielgeneratie. Verwaarloosbaar voor een groep van tientallen.
- **Sleutels nodig** (runtime): `ANTHROPIC_API_KEY`, `FAL_KEY`.

## 3. Flow
1. Lid opent "Bouw je profiel met AI".
2. **Chat** (htmx + SSE-streaming): lid typt zelfbeschrijving + links.
3. Agent haalt links op, stelt **max 1–2** scherpe vervolgvragen als cruciale info ontbreekt.
4. Agent levert gestructureerd profiel: headline, bio, rollen/affiliaties (label + url + beeld),
   projecten (naam + omschrijving + url + beeld), "waar ik naar zoek", tags/skills.
5. fal.ai genereert een cover op basis van de profiel-essentie (prompt afgeleid van bio/tags).
6. Lid ziet een **preview** (kosmische stijl) → bewerkt → kiest zichtbaarheid → publiceert.

> **Nooit auto-publiceren.** De AI draft; het lid bevestigt. Accuratesse + AVG.

## 4. Datamodel (additief, Alembic)
- `profile`: + `headline`, `cover_image_url`, `ai_enriched` (bool), `ai_source_text` (audit/regen).
- `offering` (bestaand, "wat ik maak"): + `url`, `image_url`, `description` → wordt "project".
- nieuw `profile_link`: `label`, `url`, `description`, `image_url`, `kind` (affiliation|build|other).
- Bestaand `need` / `tag` hergebruikt voor "waar ik zoek" + skills.

## 5. Componenten
- `app/services/ai_profile.py` — Opus 4.8 enrichment (web_fetch/web_search + structured output, streaming).
- `app/ai/image_generator.py` — `ImageGenerator`-interface + `FalImageGenerator` + no-op fallback.
- `app/routers/ai_profile.py` — GET bouwpagina, POST bericht (SSE), POST accepteren→persist.
- templates — chat-bouwflow + **herontworpen publieke profielpagina** (kosmische identiteit).
- config — `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=claude-opus-4-8`, `FAL_KEY`, `AI_ENRICH_ENABLED`.
- requirements — `anthropic`, fal-client (of httpx).

## 6. Edge cases & safeguards
- **Link onbereikbaar/geblokkeerd** → agent meldt welke links niet gelezen konden worden, gaat door.
- **Hallucinatie-guard** → systeemprompt: alleen feiten gegrond in opgehaalde content of de woorden
  van het lid; markeer onzekere items; lid reviewt vóór publicatie.
- **Refusal** (`stop_reason="refusal"`, Opus 4.8) → nette foutmelding, geen crash.
- **Kosten-/misbruik-guard** → cap op aantal fetches + `max_tokens`; één enrichment per submit; rate-limit per lid.
- **Privacy/AVG** → primair de door het lid opgegeven links; web_search spaarzaam; bronretentie +
  zelf-verwijderen; geen scraping buiten scope.
- **fal.ai faalt** → profiel werkt zonder cover (graceful).

## 7. Fasering
- **F1**: enrichment-service + schema + chat-flow + preview/bewerk/publiceer.
- **F2**: fal.ai-cover.
- **F3**: herontworpen publieke profielpagina (kosmisch) + SEO/OG.

## 8. Succescriterium
Een lid plakt een zin + paar links en krijgt binnen ~1 minuut een rijk, kloppend, mooi profiel
met echte beelden van zijn werk + een passende cover — en publiceert het na een lichte review.

## 9. Open (jouw input)
- `ANTHROPIC_API_KEY` (console.anthropic.com) + `FAL_KEY` (fal.ai) aanleveren voor de live-test.
