# 03 — AI-tool-reviews: de catalogus die zichzelf bijhoudt

**Status**: TER GOEDKEURING · **Datum**: 2026-06-21 · **Subteam 3 van 4 (eigenaar tool-review)**
**Kadert binnen**: `01-noordster.md` (de graaf is de asset; tools zijn een dimensie van die graaf).
**Leidend**: `CLAUDE.md` (ervaringsmandaat) + `docs/STYLEGUIDE.md` (kosmische diepte). Toetssteen overal:
**lage operationele last + stabiliteit** (solo-operator, mantelzorg-gebonden) en *"verrast dit iemand
die dagelijks met AI bouwt?"*.

> **TL;DR** — We laten Claude de AI-tools die leden gebruiken **automatisch reviewen**: één eerlijke,
> gestructureerde beoordeling (waarvoor goed, voor wie, sterktes/zwaktes, prijsmodel, NL/BE-relevantie),
> gegrond op de echte tool-website via de bestaande Browser Rendering + Claude-pipeline. Dit is **exact
> hetzelfde recept als `project_enrich_service`** — een nieuwe `tool_review`-kolom + service + nachtjob,
> geen nieuwe architectuur. De review wordt getoond als een **dossier in plaats van sterren**, met
> zichtbare AI-herkomst, bronvermelding en een **lid-correctie/aanvulling-pad** (de leden zijn experts —
> dát maakt de review beter in plaats van ongeloofwaardig). De onderscheidende asset is niet "weer een
> review-site", maar dat de review **gegrond is in wie hem gebruikt**: de mensen die deze tool dagelijks
> draaien zitten ín dit netwerk.

---

## 0. Hergebruik-audit (wat er AL staat — niet reinventen)

Onderbouwd door codebase-verkenning. Een tool-review is geen nieuw systeem; het is een tweede instantie
van het bestaande enrich-recept op het bestaande tool-model.

| Bestaand bouwblok | Pad | Hergebruik voor review |
|---|---|---|
| `Tool` + `profile_tool` (M2M) | `app/models/tool.py` | Het te reviewen object; M2M = signaal "wie gebruikt het" |
| `tool_service` (`get_or_create`/`set_tools`) | `app/services/tool_service.py` | Catalogus-groei blijft ongewijzigd |
| `logo_service` + **SSRF-guard** (`_safe_url`, `_guarded_get`) | `app/services/logo_service.py` | URL-validatie hergebruiken vóór elke fetch |
| `browser_render_service.markdown(url)` | `app/services/browser_render_service.py` | Grounding-bron (markdown van tool-site) |
| `project_enrich_service` (Claude-call + idempotentie) | `app/services/project_enrich_service.py` | **Sjabloon voor `tool_review_service`** |
| Nachtjob-vorm | `app/jobs/enrich_projects.py` + `scripts/nightly-jobs.sh` | Eén regel + één job-bestand erbij |
| `trigger_async`-patroon | `project_enrich_service.trigger_async` | Direct-na-toevoegen review starten |
| Anthropic-conventie | overal: `anthropic.Anthropic()`, `claude-opus-4-8`, **géén** `temperature`/`budget_tokens` | 1-op-1 overnemen (anders 400 op Opus 4.8) |

**Drie dingen die er NIET zijn en dus nieuw moeten**: (1) `description`/`category` op `Tool` — het model is
kaal (`name`/`slug`/`url`/`logo_url`); (2) admin-CRUD voor tools (catalogus groeit organisch via lid-input
+ seed); (3) token/kosten-metering (geen enkele service leest `message.usage`). Punt 3 is **subteam 4's
scope** — wij leveren alleen de per-review kostenschatting.

---

## 1. Scope + trigger — wélke tools, wanneer

**Principe**: review alleen tools met **echt signaal**, niet de hele wereld. De waarde is dat een review op
dewereldvan.ai *gegrond is in wie hem gebruikt* — een tool die geen enkel lid noemt, hoort hier niet thuis.

### Welke tools (de drempel)
Een `Tool` komt in de review-wachtrij zodra **álle** geldt:
1. **≥ 1 lid gebruikt hem** — er bestaat ≥ 1 rij in `profile_tool`. (Seed-tools zonder gebruiker worden
   *niet* gereviewd; ze bestaan alleen als suggestie-vocabulaire.)
2. **`url` is gevuld en valide** — zonder bron-URL kan Claude niet gronden. Geen URL → geen review (wel een
   nette "nog geen review"-staat in de UI, met een lid-knop "Vul de website aan").
3. **`tool_review` is `NULL`** (nog nooit gereviewd) **óf** ouder dan de re-review-drempel (zie §3).

> **Waarom de ≥1-gebruiker-drempel en niet "alle 30 seed-tools"?** Een review van een tool die niemand in dit
> netwerk draait, voegt niets toe dat een Google-zoek niet al geeft — en kost tokens + onderhoudslast voor
> nul netwerk-waarde. De drempel houdt de catalogus klein, actueel en *van ons*. Verworpen.

### Trigger (twee paden, beide idempotent)
- **Direct (warm pad)**: wanneer een lid een tool aan zijn profiel koppelt en die tool nog geen review heeft,
  start `tool_review_service.trigger_async(tool_id)` — net als projecten nu async verrijken. Lid ziet binnen
  ~1 min een review verschijnen (htmx-poll/SSE, hergebruik bestaand chip-patroon).
- **Nachtjob (vangnet + re-review)**: `refresh_all` sweep't tools die de drempel halen maar geen verse review
  hebben. Idempotent: draait elke nacht, doet niets als er niets te doen is.

---

## 2. Hoe AI reviewt — + accuraatheid/actualiteit-borging

### 2.1 Wat het ophaalt (grounding)
Eén bron, server-side, geen hallucinatie-ruimte:
1. **`browser_render_service.markdown(tool.url)`** → schone markdown van de tool-homepage. Gecapt op
   ~12.000 tekens (homepages + een docs/pricing-link zijn genoeg; meer = ruis + tokens).
2. **Optioneel een tweede pass** op een gedetecteerde `/pricing`- of `/docs`-link (regex op de markdown,
   dezelfde SSRF-guard als `logo_service`). Alleen als de homepage geen prijsmodel prijsgeeft.
3. **Netwerk-signaal als context (geen scraping)**: het aantal leden dat de tool gebruikt + (geanonimiseerd)
   in welke domeinen/toolsets ze zitten, gaat als gestructureerde context mee in de prompt. Dit is wat onze
   review onderscheidt: *"binnen dit netwerk vooral gebruikt door RAG/agent-bouwers"*.

### 2.2 Wat het beoordeelt (de velden)
Gestructureerde output (zie §5 datamodel), kort en eerlijk:
- **`one_liner`** — wat de tool is, in één zin, neutraal.
- **`good_for`** — waarvoor concreet goed (2-4 use-cases, geen marketing).
- **`for_whom`** — voor welk type maker (bv. "solo-builders die snel willen prototypen" vs "teams met
  compliance-eisen").
- **`strengths`** / **`limitations`** — eerlijk en specifiek. **`limitations` mag nooit leeg zijn** — een
  review zonder zwaktes is een advertentie en is dodelijk voor geloofwaardigheid bij deze doelgroep.
- **`pricing_model`** — vorm, niet exacte prijzen ("gratis tier + usage-based"; geen "$20/mnd" dat morgen
  klopt-niet-meer). Bij onbekend: expliciet `null` → UI toont "prijsmodel onbekend", niet een gok.
- **`nlbe_relevance`** — datalokatie/AVG, NL/BE-support, of het hier breed gebruikt wordt — alleen invullen
  als de bron het ondersteunt, anders weglaten (geen verzonnen "GDPR-compliant").
- **`confidence`** (`high`/`medium`/`low`) — hoe goed de bron de review onderbouwde. Stuurt de UI-toon.

### 2.3 Hoe we onjuiste / te-promotionele claims voorkomen (de kern)
De leden zijn experts; een foute of marketing-achtige review is erger dan geen review. Vijf borgingen:

1. **Strikte grounding-instructie** (zoals `project_enrich_service` al doet): *"Gebruik UITSLUITEND wat in de
   aangeleverde tekst staat. Verzin geen features, prijzen of integraties. Onbekend → laat leeg / `null`."*
2. **Anti-marketing-instructie**: *"De homepage is marketingmateriaal. Herformuleer naar nuchtere,
   verifieerbare taal. Neem superlatieven niet over. `limitations` is verplicht en mag geen holle frase zijn."*
3. **Gestructureerde output** (`output_config.format`, json_schema) — geen vrije tekst die wegdrijft; elk veld
   heeft een vaste vorm, `limitations` is `required`, en velden mogen expliciet `null` zijn i.p.v. gegokt.
4. **`confidence` + bron-stempel** — elke review toont *"AI-review op basis van \<host\> · \<datum\>"* en bij
   lage confidence een zichtbaar *"beperkt onderbouwd"*-label. Transparantie is zelf een borging.
5. **Lid-correctie als override** (zie §4) — de experts in het netwerk kunnen een veld corrigeren/aanvullen;
   die correctie wint en wordt apart getoond. Dit verandert een risico (experts die fouten zien) in de
   sterkste feature (experts die de review beter maken).

> **Bewust geen web_search / server-tools.** `project_enrich_service` koos al bewust een platte
> markdown-call boven server-tools om de `pause_turn`/cross-turn-replay-valkuilen te vermijden (zie memory
> `dewereldvan-ai-engine-constraints`). Wij volgen dat: één gegronde call op opgehaalde markdown, geen
> agentische tool-loop. Lagere kost, geen valkuilen, en de grounding is strakker (één bron, traceerbaar).

---

## 3. Cadans + kosten-schatting

### 3.1 Re-review-cadans
- **Default re-review na 90 dagen.** AI-tools veranderen snel (prijs, features), maar 90 dagen houdt de kost
  laag en de last nul. De nachtjob selecteert tools waarvan `tool_reviewed_at` ouder is dan 90 dagen *en* die
  nog ≥1 gebruiker hebben.
- **Trigger-re-review bij URL-wijziging**: als een lid de `tool.url` aanpast, nul `tool_review` → her-review
  (zelfde conventie als projecten: URL-edit nult de verrijking).
- **Geen re-review on-demand-knop voor bezoekers** (kostenbeheersing) — wél een admin/owner-knop "ververs nu".

### 3.2 Kosten per review (eerlijke math)
Prijs Opus 4.8 (bevestigd via claude-api skill, 2026-06-21): **$5,00 / 1M input · $25,00 / 1M output**.

Per review, één Claude-call:
- **Input**: ~12.000 tekens markdown ≈ **~4.000 tokens** + system/prompt + netwerk-context ≈ **~4.500 tokens**.
- **Output**: gestructureerd JSON, ~7 korte velden ≈ **~500 tokens**.
- **Adaptive thinking** (aan, zoals aanbevolen): reken ruim **~2.000 thinking-tokens** (gefactureerd als output).

| Post | Tokens | Kost |
|---|---|---|
| Input | ~4.500 | 4.500 × $5 / 1M = **$0,0225** |
| Output (incl. thinking) | ~2.500 | 2.500 × $25 / 1M = **$0,0625** |
| **Per review (Claude)** | | **≈ $0,085** (~€0,08) |
| Browser Rendering (CF) | 1-2 markdown-calls | verwaarloosbaar (CF Browser Rendering-quota; geen per-call €) |

**Schaal**: bij ~50 actief-gebruikte tools en 90-daagse re-review ≈ 50 reviews/kwartaal ≈ **~$4,25/kwartaal
(~€4/kwartaal)** aan AI-kost voor de hele catalogus. Plus de eenmalige cold-start (alle ~50 in één nacht ≈
**~$4,25**). **Dit valt ruim binnen elke budgetgrens** en raakt het €50/week-bezoekersbudget niet — reviews
draaien in de **nachtjob op operator-account**, niet op bezoeker-budget. (De metering die bezoeker-AI van
operator-AI scheidt is subteam 4; wij markeren reviews simpelweg als *systeem-job*, niet *bezoeker-actie*.)

### 3.3 Low-op-last-garantie
- **Idempotent** (`refresh_all` selecteert op `NULL`/verouderd) — herstart-veilig, geen dubbel werk.
- **Best-effort, geen `set -e`** — een falende review-fetch laat de rest van de nachtjob draaien (zoals nu).
- **Eigen sessie per tool** (`enrich_one`-patroon) — één kapotte tool-site faalt geïsoleerd.
- **Zombie-vangnet** bestaat al voor discovery-runs; reviews zijn synchroon-binnen-job dus simpeler (geen
  langlopende run-state nodig).

---

## 4. Presentatie — kosmisch + intelligent, niet generiek-sterren

**Anti-pattern dat we expliciet vermijden**: een 1-5 sterren-rating. Sterren zijn nietszeggend voor experts,
nodigen uit tot vergelijken-op-getal, en suggereren een objectiviteit die een AI-review niet heeft. We tonen
**een dossier, geen score.**

### 4.1 Het concept: "AI-dossier"
Op de tool (in de toolset-pill-context én op een eventuele tool-detail-surface) materialiseert de review als
een **kosmisch kaart-dossier** in de bestaande identiteit (indigo glas, `--line`-rand, Fraunces-kop,
JetBrains-Mono-labels, goud-accent spaarzaam):
- **Kop**: tool-naam + logo (bestaand `_cosmic_tools`-fallback-tile als geen logo).
- **Eyebrow (mono, goud)**: `AI-REVIEW · <host> · <datum>` — herkomst meteen zichtbaar.
- **`one_liner`** als lead.
- **Labelblokken**: *Goed voor* / *Voor wie* / *Sterk* / *Let op* / *Prijsmodel* / *NL/BE* — elk een kort
  mono-label + body. *Let op* (limitations) krijgt bewust evenveel gewicht als *Sterk* — eerlijkheid is de feature.
- **Netwerk-strip**: *"Gebruikt door N leden in dit netwerk"* (+ evt. de domeinen) — dít is wat geen andere
  review-site kan tonen en wat de review gronden geeft.
- **Confidence-toon**: bij `low` een subtiele *"beperkt onderbouwd — help dit aan te vullen"*-nudge (superslim-as).
- **Motion**: gestaggerde reveal (eyebrow→kop→labels), `prefers-reduced-motion`-safe; hergebruik
  `data-reveal-scroll`/`materialize` uit v0.49.0.

### 4.2 Transparantie dat het AI is
Niet weggestopt: de eyebrow *"AI-REVIEW"* staat altijd bovenaan, plus een micro-tooltip/disclosure
*"Gemaakt door Claude op basis van de tool-website. Klopt iets niet? Vul aan."* — heldere, gewone taal
(geen zweverigheid), conform STYLEGUIDE §3.

### 4.3 Mogen leden corrigeren/aanvullen? — Ja, en dat is het punt
Een altijd-bereikbaar **"Vul aan / corrigeer"**-pad op de review (sluit aan op de "feedback overal"-eis uit
STYLEGUIDE §4 en de bestaande feedback-feature):
- Een lid kan per veld een **correctie/aanvulling** indienen (vrije tekst, kort).
- Owner-/expert-correcties worden **apart getoond** onder het AI-blok: *"Aangevuld door \<lid\>"* — de mens
  overschrijft de AI niet stilletjes, beide zijn zichtbaar (geloofwaardigheid + attributie).
- Lichtgewicht: geen zware moderatie-queue; admin kan verbergen (hergebruik bestaand moderatie-patroon).

> **Waarom mens-naast-AI en niet mens-vervangt-AI?** Stille overschrijving verbergt de bron en maakt de
> review weer een black box. Naast-elkaar toont *dat* het netwerk de review aanscherpt — precies de
> noordster-belofte (de waarde is wie er ín zit). Verworpen: AI-only (mist de expert-correctie die de
> doelgroep juist kan leveren) en mens-only crowdsourcing (te hoge op-last, koud-start-probleem).

---

## 5. Concreet — datamodel, pipeline, UI

### 5.1 Datamodel (voortbouwend op `Tool`, geen breaking change)
Velden toegevoegd aan het bestaande `tool`-model (Alembic-migratie). **Bewuste afwijking van de
NULL-kolom-conventie**: we voegen wél een expliciete `tool_reviewed_at` + `tool_review_status` toe, omdat
reviews — anders dan project-summaries — een **re-review-cadans** en een **fail-zichtbaarheid** nodig hebben
(90-daagse veroudering kun je niet uit één NULL-kolom afleiden).

```
tool (bestaand):  id, name, slug, url, logo_url, created_at, updated_at
+ tool_review:        JSONB  nullable   # de gestructureerde review (zie schema)
+ tool_reviewed_at:   datetime nullable # wanneer voor het laatst gereviewd (cadans-selectie)
+ tool_review_status: str  nullable     # 'ok' | 'failed' | 'no_source'  (fail-zichtbaarheid)
```

`tool_review` JSON-schema (= `output_config.format`):
```
{ one_liner: str, good_for: [str], for_whom: str,
  strengths: [str], limitations: [str],            # limitations required, non-empty
  pricing_model: str|null, nlbe_relevance: str|null,
  confidence: "high"|"medium"|"low" }
```

Lid-correcties: nieuw lichtgewicht model `tool_review_note` (`id`, `tool_id` FK, `profile_id` FK, `field`
nullable, `body`, `created_at`, `hidden` bool) — analoog aan bestaande feedback/ideeën-modellen.

### 5.2 Pipeline / flow
```
trigger (lid koppelt tool  ─┐
          óf nachtjob)      │
                            ▼
   tool_review_service.review(tool):
     0. guard: url valide (logo_service._safe_url) → anders status='no_source'
     1. md = browser_render_service.markdown(tool.url)         # grounding
        (optioneel 2e pass op /pricing|/docs link, zelfde guard)
     2. context = netwerk-signaal (n gebruikers + domeinen, geanonimiseerd)
     3. msg = anthropic.Anthropic().messages.create(
            model="claude-opus-4-8",
            thinking={"type":"adaptive"},                      # GEEN temperature/budget_tokens
            output_config={"format": {json_schema}},
            system=REVIEW_SYSTEM,                              # grounding + anti-marketing
            messages=[{"role":"user","content": md[:12000] + context}])
     4. parse → tool.tool_review = json; tool_reviewed_at = now(); status='ok'
        (refusal/parse-fail → status='failed', laat oude review staan)
   commit (caller)
```
- `review_one(tool_id)` — eigen sessie, best-effort, nooit raisen (kopie van `enrich_one`).
- `refresh_all(db)` — selecteert `EXISTS(profile_tool) AND url IS NOT NULL AND (tool_reviewed_at IS NULL OR
  tool_reviewed_at < now()-90d)`. Idempotent.
- `trigger_async(tool_id)` — daemon-thread + in-proces dubbel-werk-guard (kopie van projecten).
- **Nachtjob**: nieuw `app/jobs/review_tools.py` (kopie van `enrich_projects.py`) + één regel in
  `scripts/nightly-jobs.sh`.

### 5.3 UI-concreet (templates, hergebruik identiteit)
- **`_cosmic_tools.html`** (bestaand): tool-pill krijgt een subtiele indicator als er een review is
  (bv. een goud micro-stipje), klik → opent het dossier.
- **Nieuw `_tool_review.html`**: het kaart-dossier (§4.1), include-baar op tool-pill-popover én op een
  toekomstige tool-detail-surface (agent-shell `surface`-registry).
- **Lege/fail-staten**: `no_source` → *"Nog geen review — de website ontbreekt. Vul aan."*; `failed` →
  stil (toon laatste goede review of niets, geen foutmelding aan bezoeker).
- **Correctie-pad**: `_tool_review_note_form.html` (htmx-patch), hergebruik feedback-styling.

---

## 6. Fasering

| Fase | Wat | Succescriterium |
|---|---|---|
| **A — Engine** | Migratie (`tool_review`/`_at`/`_status` + `tool_review_note`); `tool_review_service` (kopie enrich); nachtjob + `nightly-jobs.sh`-regel; tests (SQLite, mock Claude). | `refresh_all` reviewt alle ≥1-gebruiker-tools idempotent; eerlijke `limitations` aanwezig; refusal/parse-fail laat oude review staan. |
| **B — Presentatie** | `_tool_review.html` dossier + indicator op `_cosmic_tools`; AI-herkomst + confidence-toon; reveal-motion; lege/fail-staten. | Een lid ziet op zijn toolset een kosmisch AI-dossier mét bron + datum; haalt STYLEGUIDE §6-checklist. |
| **C — Mens-naast-AI** | `tool_review_note` correctie-pad; owner/admin "ververs nu"; admin-verberg. | Een expert-lid corrigeert een veld; correctie staat zichtbaar náást de AI-review; admin kan verbergen. |
| **D — Netwerk-grounding (fast-follow)** | Netwerk-strip ("N leden / domeinen") prominenter; filter ledengids op tool-review-eigenschappen (bv. "tools goed voor RAG"). | Review toont netwerk-context die geen externe site heeft; ledengids-filter benut review-velden. |

---

## 7. Aanbeveling + verworpen alternatieven + risico's

### Aanbeveling
**Bouw fase A+B als AUGMENT op `project_enrich_service`**: een `tool_review`-kolom + `tool_review_service`
(kopie) + één nachtjob, met gestructureerde, gegronde, eerlijke output, getoond als **AI-dossier (geen
sterren)** met zichtbare herkomst. Voeg in fase C het **mens-naast-AI-correctiepad** toe — dat zet het
expert-publiek (het grootste geloofwaardigheidsrisico) om in de sterkste feature. Kost is verwaarloosbaar
(~€0,08/review, ~€4/kwartaal voor de hele catalogus), draait unattended in de nachtjob, raakt het
bezoeker-budget niet. **Ik begin met fase A tenzij je vetoert.**

### Verworpen alternatieven (1 regel elk)
- **Sterren-/cijfer-rating** — nietszeggend en vals-objectief voor experts; vervangen door het dossier.
- **Crowdsourced reviews (mens schrijft)** — te hoge op-last + koud-start; mens komt als *correctie* bovenop AI.
- **Server-tool/web_search-agent-review** — `pause_turn`/replay-valkuilen + hogere kost; één gegronde markdown-call wint.
- **Alle seed-tools reviewen** — nul netwerk-waarde voor ongebruikte tools; drempel = ≥1 gebruiker.
- **Exacte prijzen tonen** — verouderen snel en maken de review onbetrouwbaar; alleen prijs-*model*.
- **Mens overschrijft AI stil** — verbergt de bron; mens-naast-AI houdt herkomst + attributie zichtbaar.

### Risico's
1. **Een onjuiste review schaadt geloofwaardigheid** (hoogste risico). Mitigatie: strikte grounding +
   anti-marketing-prompt, `null` bij onbekend, zichtbare `confidence` + bron, en het correctie-pad.
2. **Tool-site blokkeert/leeg (JS-heavy, paywall)** → lege markdown → zwakke review. Mitigatie: `confidence:low`
   + `no_source`-staat; nooit gokken; lid kan aanvullen.
3. **SSRF via tool-URL** (leden voeren willekeurige URLs in). Mitigatie: hergebruik `logo_service._safe_url`/
   `_guarded_get` vóór élke fetch — niet opnieuw bouwen.
4. **Stale review na tool-pivot** — 90-daagse cadans + URL-edit-nullt-review vangen het meeste; expert-correctie
   vangt de rest sneller dan elke cadans.
5. **Prompt-injection vanuit de homepage-markdown** (tool-site stopt "negeer instructies" in de tekst).
   Mitigatie: gestructureerde `output_config.format` (geen vrije gehoorzaamheid), grounding-only-instructie,
   en de markdown wordt als *data* aangeboden, niet als instructie.
```