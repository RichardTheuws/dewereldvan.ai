# PRD — Discovery: de footprint-engine + de live ontdekkings-ervaring

**Status**: ter goedkeuring · **Versie doc**: 1.0.0 · **Datum**: 2026-06-20
**Aanleiding**: Richards visie (2026-06-20): vraag de AI om je profiel op te
bouwen → hij doet een slimme web-search, snapt of een link ÉCHT met jou te maken
heeft (eigen project / media / blog / overig), zoekt evt. beelden, en toont dat in
een grote, futuristische live-animatie waarin beelden en tekst voorbijvliegen.

## Het inzicht: één gedeelde engine, twee consumenten
De intelligente kern — **"is dit ECHT jij?"** (zoeken → entity-resolution →
classificeren) — is één **footprint-engine** (`footprint_service`). Twee consumenten:
- **Discovery** (deze PRD): het grote, **live-streamende** onboarding-moment.
- **De Scout** (eigen PRD): dezelfde engine, periodiek, die NIEUWE bevindingen
  proactief voorstelt om te koppelen (via de getekende-actie-laag → Telegram/MCP/canvas).

Discovery bouwt de engine; de Scout hergebruikt 'm. Daarom Discovery eerst.

## Waarom dit ECHT vooruitstrevend is (en niet "search + resultaten tonen")
Het verschil zit in twee dingen die elkaar versterken:
1. **De intelligentie = entity-resolution.** Niet links dumpen, maar per resultaat
   beslissen of het écht deze persoon is (Jan de Vries de AI-bouwer ≠ de tandarts),
   mét confidence + classificatie. Daar faalt de markt; goed disambigueren = de moat.
2. **De ervaring = de redenering zichtbaar gemaakt.** De "brainstorm waarin beelden
   en tekst voorbijvliegen" is de échte zoektocht live: queries vuren, kandidaten
   stromen binnen, worden gewogen/geaccepteerd/verworpen, en crystalliseren tot je
   profiel. De animatie ÍS de intelligentie — geen losse lichtshow (mandaat: verbaas
   door ervaring én intelligentie, nooit een trucje vermomd als ervaring).

## Niet-doelen (v1)
- Geen ontdekking van/over ánderen — strikt **zelf-ontdekking** (consent inherent).
- Geen gezichtsfoto-scraping in v1 (AVG-gevoelig → Fase 3); v1 = werk/projectbeeld
  (screenshots via de bestaande CF-pijplijn).
- Geen nep-animatie: elk beeld/woord dat voorbijvliegt is een echt zoekresultaat/
  echte verdict-stap.

## Het ontwerp

### 1. Seed & disambiguatie (hoe beter de seed, hoe scherper de resolutie)
Inputs: je naam + bekende links (site/GitHub/LinkedIn uit je profiel) + optioneel
een **anker-zin** die je zelf geeft ("ik ben degene die aan X werkt / in stad Y").
De eerste eigen link is goud: het identiteits-anker waartegen we corroboreren.

### 2. Live zoek-loop (streaming) — de ervaring
Hergebruikt de bestaande SSE-machinerie (concierge/profielbouw) + de materialisatie-
animatie. De engine zendt **echte events**; de frontend rendert daaruit het
voorbijvliegen + crystalliseren:
- `search` — een query draait ("zoekt naar … op het web");
- `candidate` — een resultaat gevonden (titel, snippet, thumbnail);
- `verdict` — geaccepteerd/verworpen + waaróm + confidence (de zichtbare redenering);
- `classify` — type (project / media / blog / talk / sociaal / overig);
- `crystallize` — toegevoegd aan je wordende profiel.
De wachttijd ÍS de show: latency van zoeken/fetchen wordt de cinematic.

### 3. Entity-resolution (de intelligentie, grounding-poort)
Per kandidaat verzamelen we corroboratie-signalen (linkt het naar/van je ankers;
matcht naam + context met wat we al weten — tags, wat je maakt; domein-eigendom) →
één LLM-oordeel met **confidence**. Grounding: "dit is jij" alleen bij corroboratie;
confidence wordt getoond. **Human-in-the-loop** als accuratesse- én AVG-poort:
- hoge confidence → crystalliseert live, met makkelijke **undo**;
- lage/twijfel → in een "klopt dit?"-rij die je expliciet bevestigt/verwerpt.
Zo blijft de flow magisch zonder false-positives door te drukken.

### 4. Classificatie → bestaande entiteiten (voedt de graaf)
- **eigen project** → `Offering` — mét de screenshot-hero + AI-samenvatting die we
  net live zetten (de discovery hangt er de echte link aan, de enrich-pijplijn doet
  de rest, direct via `trigger_async`).
- **media (over jou)** → `nieuws`-`Post` met de bestaande **rol-badge**
  (geïnterviewd / vermeld / gedeeld).
- **blog/talk (door jou)** → link of nieuws-item.
Aangemaakt als concept dat je bevestigt (tonen + 1-klik), of auto met undo bij hoge
confidence. Discovery verrijkt dus niet alleen je profiel — het verdiept de hele graaf.

### 5. Beelden
Werk/projectbeeld via de bestaande CF-screenshot-pijplijn (per bevestigde link).
Gezichtsfoto's van een persoon: **Fase 3**, alleen met expliciete keuze + AVG-zorg.

## Honest over de moeilijke delen (eerlijke math)
1. **Live-streaming-orkestratie** van zoeken + redeneren + beeld is fors bouwwerk
   (de zware route die je koos). De winst: maximale, échte wow.
2. **False positives zijn dodelijk** voor een expert → de human-confirm-poort +
   confidence + undo zijn niet-onderhandelbaar.
3. **Kosten/latency**: meerdere searches + fetches + LLM per ontdekking. Mitigatie:
   gefaseerd zoeken (eerst ankers, dan breder), cachen, caps; de animatie maskeert
   latency. Gegated op `AI_ENRICH_ENABLED`.
4. **AVG**: zelf-only; niets gepubliceerd zonder klik; persoonsbeeld pas Fase 3 met
   consent; alles mee gewist bij account-verwijdering.

## Hergebruik-audit (groot)
| Bouwsteen | Status |
|---|---|
| web_search/web_fetch-loop + materialisatie | `ai_profile` ✓ |
| SSE-stream-machinerie (events → animatie) | concierge/profielbouw ✓ |
| screenshot + samenvatting per link | CF Browser Rendering + `project_enrich_service` ✓ (vandaag) |
| classificatie-doelen (Offering / nieuws-Post + rol-badge) | model ✓ |
| tonen + 1-klik bevestigen | draft-surfaces ✓ |
| fal-sfeerbeeld (gegrond) | `cover_art_service` ✓ (vandaag) |
| **nieuw** | `footprint_service` (search → entity-resolution → classify), de live-discovery-SSE-route + animatie, de "klopt dit?"-bevestigrij |

## Fasering
- **Fase 1**: de footprint-engine + de live-streamende discovery als expliciete
  profiel-actie ("Zal ik je online opzoeken en je profiel opbouwen?") → zoek →
  resolve → classify → crystalliseer → bevestig. De onboarding-wow + de foundation.
- **Fase 2**: de **Scout** hergebruikt de engine continu (nieuwe bevindingen →
  voorstel om te koppelen via de getekende-actie-laag → Telegram/MCP/canvas). Zie de
  Scout-PRD.
- **Fase 3**: persoonsbeeld (met consent), diepere bronnen, agent-triage (jouw eigen
  agent koppelt de zekere automatisch, escaleert twijfel).

## Succescriteria & KILL-condities
- **Succes**: een lid typt z'n naam/een link en kijkt toe hoe een gegrond, geverifieerd
  profiel zich live opbouwt — en zegt "wow". Gemeten: completeness-sprong na discovery;
  fractie kandidaten die het lid bevestigt (precisie van de entity-resolution).
- **KILL** de auto-crystallisatie als de precisie laag is (leden verwerpen structureel)
  → val terug op confirm-everything; de engine zelf blijft, de auto-magie niet.

## Beslissingen (jouw call — vorm de spec)
1. **Auto-crystalliseren bij hoge confidence (met undo) vs alles expliciet bevestigen.**
   Aanbeveling: auto boven een hoge drempel + undo (houdt de live-flow magisch),
   twijfel naar de bevestigrij. Conservatieve drempel om false-positives te weren.
2. **Persoonsbeeld in v1?** Aanbeveling: nee — Fase 3 (AVG). v1 = werk/projectbeeld.
3. **Zoek-bron**: Anthropic web_search (zit al in `ai_profile`) als basis; evt. later
   Brave/Tavily voor bredere recall. Aanbeveling: start met wat er is.
