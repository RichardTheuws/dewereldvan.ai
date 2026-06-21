# Visie 02 — Nieuws & Content

> Subteam 2 (van 4). Beslis-klare notitie. Bouwt **AUGMENT** op het bestaande
> `Post`-model (`kind=nieuws`), de bestaande nachtjob-infra (`scripts/nightly-jobs.sh`,
> `enrich_projects`, `distill_memories`) en de Discovery-footprint-engine
> (`footprint_service`, web_search/web_fetch server-tools op `claude-opus-4-8`).
> **Geen tweede look** — alles in de bestaande kosmische identiteit (`cosmic.css`).

**Status**: voorstel · **Datum**: 2026-06-21 · **Versie-context**: 0.49.1

---

## 0. Kern-aanbeveling (TL;DR)

Maak nieuws **niet** een aggregator-feed maar een **wekelijkse, AI-gecureerde briefing
met duiding-per-item én verbanden naar leden/tools**. De bestaande lid-bijdrage-flow
(`POST /nieuws`) blijft; daarbovenop komt één nachtelijke `curate_news`-job die ~6–10
items per week voorstelt, elk met een korte "waarom dit ertoe doet voor de groep"-zin
en een gedetecteerde link naar leden of tools in de DB. Een mens (admin) keurt de
shortlist met één klik goed — **geen volautomatische publicatie** (false positive =
dodelijk voor dit expert-publiek, exact zoals de Discovery-engine al redeneert met
`HIGH_CONFIDENCE=90`).

Eén nieuwe presentatievorm: **"De Briefing"** — een wekelijkse kosmische
constellatie-strip waar items als sterren verschijnen, met AI-duiding die uitvouwt en
verbindingslijnen naar de leden/tools die het raakt. Per item AI-kost ≈ **€0,01–0,03**;
wekelijkse curatie-batch ≈ **€0,15–0,40**. Ruim binnen elk budget.

---

## 1. Wat hoort hier (in / out)

De lat (uit `CLAUDE.md` + `STYLEGUIDE.md`): de leden zijn de scherpste AI-makers van
NL/BE. Nieuws dat zij **zelf al gezien hebben** voegt niets toe — het moet sneller,
scherper geduid, of dichter-bij-de-groep zijn dan hun eigen feeds.

### IN — relevant voor déze makers
- **NL/BE AI-beleid & regulering** met directe impact op bouwers: AI Act-handhaving
  (transparantieregels van kracht aug 2026), nationale AI-strategie, subsidies/SBIR,
  toezichthouders (AP, RDI), data/privacy-uitspraken. *Dit is concreet en NL-specifiek —
  precies wat internationale feeds missen.*
- **Wat leden zelf doen**: een lid lanceert iets, wordt geïnterviewd, geeft een talk,
  haalt funding, wordt uitgelicht. Dit is de **kern-differentiator** — bestaat al als
  `NewsRole` (geschreven/geïnterviewd/vermeld/gedeeld) en sluit aan op de
  Discovery-media-pass die al interviews/artikelen óver leden vindt.
- **Tools & releases die de groep gebruikt of zou moeten kennen** — gekoppeld aan de
  bestaande Tool-catalogus (`tool` model, `profile_tool` M2M). "Model X heeft nu Y" telt
  alleen mee als het verandert hoe je bouwt, en idealiter met een verband naar wie in de
  groep die tool al inzet.
- **NL/BE AI-events & meetups** — overlapt met `kind=event` (agenda); nieuws verwijst
  ernaar, geen duplicatie.
- **Substantieel onderzoek** met praktische gevolgen (papers/benchmarks die een
  bouwkeuze verschuiven), niet academische ruis.

### OUT — wat dit NOOIT wordt
- **Generieke tech-/AI-nieuwsaggregator.** Geen "OpenAI kondigt aan…"-stroom die op
  elke site staat. Als het op TechCrunch/Tweakers staat zonder NL/BE-hoek of
  groeps-verband → niet plaatsen.
- **Hype, listicles, "10 prompts die…", thought-leadership-marketing.**
- **Internationaal nieuws zonder NL/BE-relevantie of leden-/tool-verband.**
- **Volume.** Liever 6 scherpe items/week dan 40 lauwe. Schaarste = signaal.

**Redactionele toets per item** (de AI-filter hanteert dit, zie §2):
*"Zou een lid dat dagelijks met AI bouwt dit nog niet weten — en verandert het wat
voor de groep?"* Nee → drop.

---

## 2. Sourcing + automatisering (lage op-last)

### Principe
Richard is solo + mantelzorg → **unattended draaien, 1-klik admin-poort, nooit
silent-publish**. Dit spiegelt exact de bestaande Discovery-keten (achtergrond-job →
confidence → hoge-zekerheid auto met undo / twijfel naar 1-klik-bevestigrij).

### Drie bronnen, oplopend in waarde
1. **Lid-bijdragen** (bestaat al): `POST /nieuws`, direct zichtbaar, rate-limited,
   admin-hide. Blijft ongewijzigd — dit is de hoogste-signaal bron (een lid deelt iets
   omdat het ertoe doet). **AUGMENT, niet vervangen.**
2. **AI-curatie van het web** (nieuw): een nachtjob `curate_news` die met de **bestaande
   web_search/web_fetch server-tools** op `claude-opus-4-8` (zoals `footprint_service`
   al doet — zelfde SDK-contract: adaptive thinking, server-tool-loop, geen temperature)
   een vaste set NL/BE-bronnen + gerichte queries afgaat, en per kandidaat een
   `record_news_item`-tool invult (titel, url, bron, 1-zin-waarom, relevantie-score,
   gedetecteerde leden/tool-match). Output = **voorstellen**, niet live.
3. **Leden-gekoppelde media** (nieuw, fast-follow): hergebruik de Discovery-media-pass
   (`focus="media"`) die al interviews/artikelen óver een lid vindt → kandidaat-nieuws
   met `role=vermeld/geinterviewd` en `added_by` automatisch gelinkt. Hoogste verbazing:
   "wij zagen dat jij in [bron] stond" — de site weet het vóór jij het deelt.

### De filter (hoe AI op relevantie/kwaliteit selecteert)
De `curate_news`-prompt krijgt:
- de **redactionele toets** uit §1 (in/out hard gespecificeerd),
- een **dedup-context**: titels/urls van reeds-geplaatste posts uit de laatste ~60 dagen
  (zodat niets dubbel komt — spiegelt de Discovery-`append + dedup`),
- een **groeps-context**: de actieve tags, tool-catalogus en (geanonimiseerd) waar de
  groep mee bouwt, zodat de AI verbanden kan leggen,
- een **score-drempel**: alleen items ≥ drempel komen op de shortlist; net als
  Discovery's `HIGH_CONFIDENCE` conservatief hoog (een zwak item is erger dan een gemist
  item bij dit publiek).

### Op-last & cadans
- **Wekelijks**, niet dagelijks: één `curate_news`-run per week (bv. zondagnacht via de
  bestaande LaunchAgent naast `nightly-jobs.sh`). Dagelijks zou te veel admin-poort-werk
  en te veel lauwe items geven. Wekelijks past bij "schaarste = signaal".
- **1-klik admin-shortlist**: de run schrijft kandidaten als `Post` met een nieuwe staat
  `pending_review` (zie §4). Admin ziet ze in dezelfde admin-queue-stijl als
  ledengoedkeuring; goedkeuren = `hidden=False` zichtbaar, weigeren = weg. **Geen
  e-mail** (memory `notificaties`: alleen magic-link per mail) → in-app chip +
  optioneel Telegram-push ("3 nieuws-kandidaten klaar").
- **Best-effort & idempotent**: een fout in de AI-laag breekt niets (zelfde discipline
  als `nightly-jobs.sh` zonder `set -e`). Dubbele run = geen dubbele items (dedup-context).

---

## 3. Presentatieconcept — hoe het verbaast

De huidige `/nieuws` is een nette kaartenlijst (rol-badge + bron + datum). Dat is een
**lijst** — voor dit publiek een regressie. De verbazing moet uit **ervaring +
intelligentie** komen (niet uit zweverige taal — in-app blijft eenvoudig en direct,
conform `STYLEGUIDE.md` §3).

### "De Briefing" — één kosmische presentatievorm
1. **AI-duiding per item ("waarom dit ertoe doet").** Elk item toont onder de kop één
   heldere zin: *niet* een samenvatting van het artikel, maar **wat het betekent voor
   jou/voor de groep**. Bv. "De AI Act-transparantieregels gelden vanaf augustus — als je
   user-facing AI bouwt, raakt dit je labelling." Dit is de intelligentie die een kale
   feed mist. Gegenereerd door de curatie-job, dus gratis bij weergave.
2. **Verbanden naar leden/tools (het handtekening-element).** Als een item een lid of
   een tool uit de catalogus raakt, toont de kaart dat als een **verbindingslijn** in de
   bestaande constellatie-taal: "raakt [tool X] — die [3 leden] gebruiken" of "[lid Y]
   wordt hierin genoemd". Dit hergebruikt letterlijk de "netwerk van makers"-metafoor uit
   het teaser-canvas (`STYLEGUIDE.md` §1) en maakt nieuws **van de groep**, niet over de
   wereld. Geen enkele andere AI-nieuwsplek kan dit — het is de moat.
3. **Constellatie-reveal.** Items verschijnen als sterren die indrijven
   (`data-reveal-scroll` / `materialize`-variant uit v0.49.0), met de duiding die
   uitvouwt op hover/tap en de verbindingslijn die oplicht naar de geraakte
   ster(ren)/tool(s). Volledig `prefers-reduced-motion`-safe (animaties uit → alles
   direct leesbaar).
4. **"Slim, niet alleen mooi" (STYLEGUIDE §4).** De concierge-agent kan over nieuws
   praten (`concierge_context="nieuws"` bestaat al): "vat de briefing voor me samen",
   "wat raakt mijn stack?". Feedback overal blijft (`_feedback_affordance.html`).

### Personalisatie: leden vs bezoekers
- **Leden (ingelogd)**: de duiding mag persoonlijk worden — "raakt jouw tool [X]",
  "[lid in jouw netwerk] wordt genoemd". Dit gebruikt profiel/tool-data die er al is.
  Gegenereerd-op-vraag of in de nachtjob per actief lid? → **In de nachtjob, generiek per
  groep** (één duiding/item, hergebruikt), met **lichte client-side personalisatie**
  (highlight de tools die in jouw profiel staan). Zo blijft de AI-kost één-per-item, niet
  één-per-lid-per-item.
- **Bezoekers (publiek, AI-budget €50/week)**: zien de **publieke** briefing-items
  (alleen items met `visibility=publiek`; besloten items + persoonlijke duiding blijven
  login-gated, `noindex`). Geen per-bezoeker AI-generatie → kost = €0 bij weergave
  (alles vooraf gegenereerd in de nachtjob). De €50/week-meter (subteam 4) wordt dus
  **niet** belast door nieuws-weergave; alleen de wekelijkse curatie-batch telt, en die
  is operator-side, niet bezoeker-side.

### Cadans van de ervaring
Wekelijkse "drop" voelt als een gebeurtenis (vrijdag/zondag), niet een oneindige scroll.
Tussendoor blijven lid-bijdragen real-time binnenkomen. De briefing-strip bovenaan toont
"deze week"; daaronder het doorlopende archief in dezelfde kaart-taal.

---

## 4. Datamodel + UI concreet

### Datamodel — AUGMENT op bestaand `Post`
Het `Post`-model is bewust holistisch ("nieuwe contenttypes = extra enum-waarde + paar
nullable kolommen, geen tweede tabel"). We blijven binnen die filosofie.

**Nieuwe nullable kolommen op `Post`** (één Alembic-migratie):
- `review_state` (enum `PostReviewState`: `live` | `pending_review` | `rejected`,
  default `live`) — lid-bijdragen zijn `live` (huidig gedrag); AI-kandidaten starten
  `pending_review`. Zo blijft de bestaande lid-flow ongewijzigd.
- `source_kind` (enum: `member` | `ai_curated` | `member_media`, default `member`) —
  herkomst, voor weergave ("gevonden door dewereldvan") en metrics.
- `ai_relevance` (int, nullable) — de curatie-score; nullable voor lid-bijdragen.
- `ai_take` (Text, nullable) — de "waarom dit ertoe doet"-duiding (1–2 zinnen).
- `briefing_week` (Date, nullable) — de ISO-week-ankerdag, voor groepering in "De Briefing".

**Verbanden (hergebruik bestaande relaties, geen nieuwe tabel nu):**
- Leden-link: bestaande `added_by` (`Member`, SET NULL) — bij `member_media` vult de
  curatie-job dit met het herkende lid.
- Tool-link: een lichte M2M `post_tool` *kan* later (spiegelt `profile_tool`), maar voor
  MVP volstaat **detectie-op-weergave**: match de getoonde tools tegen de tool-catalogus
  op naam/url uit `ai_take`. Pas een echte `post_tool`-tabel toevoegen als de
  verbindingslijnen vaak genoeg voorkomen om persistente links te rechtvaardigen
  (YAGNI — bevraag erfgoed, voeg niet speculatief toe).

**Service-laag** (`post_service.py` AUGMENT):
- `list_news()` → splitst in `briefing_this_week` (op `briefing_week`) + `archief`.
- `list_pending_review()` → admin-shortlist (nieuw).
- `approve_news(post)` / `reject_news(post)` → `review_state`-transities + AuditLog
  (spiegelt `set_hidden`).
- `create_curated_news(...)` → door de job aangeroepen, idempotent op url.

**Nieuwe job** `app/jobs/curate_news.py` (spiegelt `enrich_projects.py`-vorm):
best-effort, gegated op `ai_enrich_enabled`, roept een nieuwe
`news_curation_service.py` aan (spiegelt `footprint_service`-SDK-patroon: web_search +
web_fetch, `record_news_item`-tool voor gestructureerde output, dedup-context,
relevantie-drempel). Toegevoegd aan `nightly-jobs.sh` (wekelijkse gate of aparte
LaunchAgent met week-cadans).

### UI — één presentatievorm, bestaande identiteit
- `nieuws/index.html`: bovenaan **"Deze week" briefing-strip** (constellatie-reveal,
  duiding + verbindingslijnen), daaronder het bestaande kaart-archief.
- `nieuws/_card.html` AUGMENT: voeg `ai_take`-blok toe (uitvouwbaar), herkomst-badge
  ("gevonden door dewereldvan" naast de bestaande rol-badges), en de
  tool/lid-verbindingschip. Géén tweede look — zelfde `news-card`-klassen + `cosmic.css`.
- Admin-shortlist: hergebruik de admin-queue-stijl (zoals ledengoedkeuring) met 1-klik
  goedkeuren/weigeren via htmx-swap (spiegelt `admin_hide`).
- In-app "klaar"-chip + optionele Telegram-push bij nieuwe shortlist (bestaande
  `notification_service` + `telegram_service`).

---

## 5. Kosten-schatting per item

Tarieven (claude-api skill, cache 2026-06): **Opus 4.8** $5 in / $25 uit per 1M tokens;
**Haiku 4.5** $1 / $5 per 1M. Server-tool `web_search` ≈ $10 per 1.000 zoekopdrachten
(Anthropic web_search), `web_fetch` server-side.

**Per gecureerd item (Opus 4.8, met web_search/web_fetch + duiding):**
- Input incl. dedup/groeps-context + opgehaalde pagina-snippets: ~8–15K tokens ⇒
  ~$0,04–0,075.
- Output (gestructureerd item + 1–2 zinnen `ai_take`): ~0,5–1K tokens ⇒ ~$0,012–0,025.
- ~1–2 web_search-calls per item ⇒ ~$0,01–0,02.
- **Per item ≈ $0,06–0,12 (≈ €0,06–0,11).** Maar: de curatie draait **één batch met
  gedeelde context** (prompt-caching op de in/out-regels + groeps-context), dus de
  marginale kost per item daalt fors. Realistisch:
- **Wekelijkse batch (1 web-pass, ~30 kandidaten beoordeeld → ~8 shortlist):**
  ~$0,20–0,50 (≈ **€0,18–0,45 per week**) met caching. Per gepubliceerd item dus
  **≈ €0,02–0,05**.

**Goedkoper alternatief voor de pure filter-stap:** de eerste relevantie-schifting
(in/out-classificatie van ruwe kandidaten) kan op **Haiku 4.5** (5× goedkoper); alleen
de shortlist krijgt de Opus-duiding. Dit drukt de batch naar **~€0,10–0,25/week** zonder
kwaliteitsverlies op de duiding. Aanbevolen zodra het kandidaten-volume groeit.

**Weergave-kost: €0.** Alle duiding is vooraf gegenereerd; bezoekers en leden triggeren
geen AI bij het lezen. Het **€50/week bezoekers-budget wordt door nieuws niet belast** —
nieuws-AI is operator-side (de wekelijkse batch), niet per-bezoeker. (Als later
per-bezoeker "vat dit voor mij samen" via de concierge komt, telt dát wél mee in de
meter van subteam 4 — buiten scope hier.)

---

## 6. Fasering

### MVP (next sprint) — "De Briefing" met mens-in-de-lus
1. `Post`-migratie: `review_state`, `source_kind`, `ai_take`, `ai_relevance`,
   `briefing_week` (nullable, lid-flow ongewijzigd).
2. `curate_news`-job + `news_curation_service` (web_search/web_fetch op Opus 4.8, vaste
   NL/BE-bronnen + queries, dedup-context, relevantie-drempel, `record_news_item`-tool).
3. Admin-shortlist (1-klik goedkeuren/weigeren, htmx-swap, AuditLog) + in-app chip /
   Telegram-push.
4. UI: briefing-strip met `ai_take` + constellatie-reveal; `_card.html` AUGMENT
   (herkomst-badge). **Tool/lid-verbanden via detectie-op-weergave** (geen nieuwe tabel).
5. Tests in dezelfde sessie (SQLite in-memory): job-idempotentie, review-transities,
   dedup, zichtbaarheid (publiek vs besloten + `noindex`), reduced-motion.

### Next — verbanden + leden-media + kosten-optimalisatie
6. **Discovery-media-pass koppelen**: `source_kind=member_media`, auto-`added_by`,
   `role=vermeld/geinterviewd` — "wij zagen jou in [bron]".
7. **Persistente tool-verbanden** (`post_tool` M2M) zodra detectie-op-weergave te vaak
   raak is om niet vast te leggen; filter nieuws op tool/lid.
8. **Haiku-voorfilter** voor de relevantie-schifting (batch-kost ↓).
9. **Lichte personalisatie** voor leden (highlight tools uit eigen profiel) — client-side,
   geen extra AI-kost.
10. Publieke showcase-haak (Fase 5 PRD): uitgelichte briefing-items met OG/JSON-LD voor
    SEO (alleen publieke items).

---

## 7. Aanbeveling + verworpen alternatieven + risico's

### Aanbeveling
Bouw **"De Briefing"**: wekelijkse AI-curatie (web_search op de bestaande Opus-keten) →
1-klik admin-shortlist → kosmische constellatie-presentatie met **duiding-per-item** en
**verbindingslijnen naar leden/tools**. Augmenteer het `Post`-model met vijf nullable
kolommen; hergebruik nachtjob-infra, Discovery-media-pass, concierge en
notificatie-kanalen. Dit verbaast door **intelligentie en verband** (niet door taal of
volume), houdt de op-last laag (unattended job + 1-klik poort, geen silent-publish),
en kost ~€0,10–0,45/week — buiten het bezoekers-budget.

*Ik begin met de MVP-fasering hierboven tenzij je vetoert.*

### Verworpen alternatieven (1 regel elk)
- **Volautomatische publicatie (geen admin-poort)** — false positive is dodelijk voor dit
  expert-publiek; de hele Discovery-engine kiest bewust mens-in-de-lus bij twijfel.
- **Dagelijkse feed / aggregator** — wordt generiek, verhoogt op-last en lauwe ruis;
  schaarste is hier het signaal.
- **Per-bezoeker live AI-samenvatting** — belast onnodig het €50-budget en voegt geen
  groeps-verband toe; vooraf-gegenereerde groeps-duiding is goedkoper én slimmer.
- **Tweede tabel / eigen nieuws-stack** — schendt de holistische `Post`-filosofie en de
  AUGMENT-regel; nullable kolommen volstaan.
- **Nieuwe visuele look voor nieuws** — verboden (`STYLEGUIDE` anti-pattern); de
  constellatie-taal bestaat al en is precies de juiste metafoor.

### Risico's
- **Curatie-kwaliteit/false positives**: de AI plaatst iets lauws of fout-geduid. →
  Mitigatie: hoge relevantie-drempel + verplichte admin-poort + dedup-context; meet de
  goedkeur-ratio (zoals Discovery-precisie al gemeten wordt) en ijk de drempel.
- **Bronnen-recht / scraping**: web_fetch haalt artikel-inhoud op. → Alleen titel + url +
  korte eigen duiding tonen (geen herpublicatie van de volledige tekst); link-out naar de
  bron (bestaand gedrag: "lezen ↗").
- **Privacy/AVG bij `member_media`**: een lid auto-koppelen aan een gevonden artikel. →
  Hergebruik de Discovery-discipline (zelf-ontdekking, lid bevestigt); een
  media-koppeling die een ander lid betreft = `pending_review`, nooit auto-live.
- **Lege-week-risico**: een week zonder goed nieuws. → Lege-staat met aandacht
  (`STYLEGUIDE` §3): "Rustige week. Iets gezien? Deel het." — lid-bijdragen vullen de gaten.
- **Drempel-drift**: te streng (lege briefing) of te los (ruis). → Eén knop in admin om de
  drempel bij te stellen; goedkeur-ratio als signaal.

---

## Pointers
- Bestaand: `app/models/post.py`, `app/services/post_service.py`,
  `app/routers/posts.py`, `app/templates/nieuws/`, `app/templates/agenda/`.
- AI-curatie-patroon om te spiegelen: `app/services/footprint_service.py`
  (web_search/web_fetch + `record_findings`-tool + dedup), `app/jobs/enrich_projects.py`,
  `scripts/nightly-jobs.sh`.
- Notificatie/concierge: `app/services/notification_service.py`,
  `telegram_service.py`, `concierge_service.py` (`concierge_context="nieuws"`).
- Identiteit: `docs/STYLEGUIDE.md`, `app/static/cosmic.css`, v0.49.0 reveal-varianten.
