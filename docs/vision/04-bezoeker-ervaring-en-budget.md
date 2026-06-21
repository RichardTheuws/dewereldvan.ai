# 04 — Bezoeker-ervaring & kosten-governance

**Status**: TER GOEDKEURING · **Datum**: 2026-06-21 · **Subteam 4 van 4 (eigenaar kosten-governance)**
**Kadert**: subteam 1 (noordster), 2 (nieuws), 3 (tool-review). Levert de **publieke voordeur** + de
**uitgaven-rem** die voorkomt dat die voordeur Richard geld kost dat hij niet heeft.
**Leidend**: `CLAUDE.md` (ervaringsmandaat), `docs/STYLEGUIDE.md` (kosmische diepte), en het harde
axioma **lage op-last + stabiliteit + geen kosten-uitloop** (solo-operator, mantelzorg, geen buffer).

> **TL;DR** — Een niet-lid moet binnen 10 seconden de **intelligentie** van het platform vóélen, niet
> erover lezen. Het scherpste, goedkoopste en minst misbruikbare concept is **"bouw live een mini-kaart
> uit één URL"**: de bezoeker plakt een link, een echte Opus-call leest de pagina en toont in de kosmische
> stijl wie deze persoon is + bij wie in het netwerk die zou passen → CTA "vraag toegang". Eén betaalde
> call per bezoeker, hard gegate door **Turnstile + per-IP daglimiet + globale weekcap (€50)** met nette
> kosmische degradatie als de pot leeg is. Spend wordt **per call** geboekt in één tabel (`ai_spend_log`)
> en Richard ziet 'm op een admin-meter; bij 80% van de weekcap een Telegram-ping. **Budget is wiskundig
> gegarandeerd**: de globale weekcap is een harde gate vóór elke call, niet een waarschuwing achteraf.

---

## 0. Waar we op voortbouwen (AUGMENT, niet REPLACE)

De engine bestaat al — alleen login-gated. Niets hieronder vraagt een nieuwe AI-stack; het vraagt een
**niet-lid-veilige variant** van wat er staat, plus een meter-laag die nu ontbreekt.

| Bestaand | Bestand | Voor niet-lid herbruikbaar? |
|---|---|---|
| Levende AI-profielbouw (Opus, SSE, web_fetch op geplakte URL) | `app/services/ai_profile.py` · `app/routers/ai_profile.py` | **Ja, ingedikt** — de URL→profiel-kern is precies het wow-concept. Nu `require_member`. |
| Concierge (Opus, tool-loop over de graaf) | `app/services/concierge_service.py` | Deels — chat-endpoint is al `current_member` (niet strikt gated), maar **ongelimiteerd**. Gevaarlijk voor niet-leden zonder cap. |
| Discovery/footprint (Opus + web_search, **duurste run**, minuten) | `app/services/footprint_service.py` | **Nee** voor niet-leden — te duur, te traag. Lid-only houden. |
| Rij-tel-rate-limit in glijdend uur (per lid / per IP) | `app/services/magic_link.py`, `registration.py`, `photo_service.py` | **Ja, als fundament** — zelfde patroon uitbreiden naar spend-metering. |

**Drie gaten die we hier dichten** (gevonden in de audit): (a) er is **geen spend/token-tracking** — geen
tabel, geen `usage`-uitlezing; (b) er is **geen Turnstile/captcha** ondanks dat Cloudflare ervóór zit; (c)
IP wordt overal als `request.client.host` gelezen — **achter de Tunnel is dat één upstream-IP**, dus per-IP
limieten zijn nu blind. Punt (c) is een blokkerende voorwaarde voor élke per-IP-cap hieronder.

---

## 1. Ervaring-concepten — wat een niet-lid ZELF kan doen

Elk concept: wow-factor · kost/call · misbruik-risico · funnel naar lidmaatschap. Kosten gerekend op
**Opus 4.8** (`claude-opus-4-8`, prijs **$5/1M input · $25/1M output**, ≈ **€4,65 / €23,25** bij 1 USD≈0,93 EUR).
Web-tools (`web_fetch`/`web_search`) draaien server-side bij Anthropic en tellen als extra input-tokens van
de opgehaalde pagina — dat is de **dominante kostenpost**, niet de system-prompt.

### Concept A — "Bouw live een mini-kaart uit één URL" ⭐ AANBEVOLEN
De bezoeker plakt een link (eigen site, GitHub, LinkedIn-post, project). Opus leest 'm via `web_fetch` en
toont — gestreamd, in kosmische stijl — **drie dingen**: (1) een korte, scherpe duiding van wie/wat dit is,
(2) welke 2-3 thema's/tools eruit springen, (3) één regel "bij dít soort makers in het netwerk zou je
passen". Daarna: *"Dit is wat onze agent voor leden dóór het hele netwerk doet. Vraag toegang."*

- **Wow**: de bezoeker ziet binnen seconden dat de site hém leest en plaatst — niet een formuliertje. Dit is
  exact de "superslim"-as uit de styleguide, niet alleen mooi.
- **Kost/call**: 1 pagina-fetch (≈ 4-15k input-tokens afhankelijk van paginagrootte) + system + ~600 output-tokens
  + adaptive thinking. Realistisch **€0,04–€0,09/call**; reken **€0,08** als bovengrens-planningswaarde.
  We **cappen de fetch** (1 URL, geen `web_search`-loop, `MAX_TOKENS≈1500`, geen pause-turns) → kosten blijven strak.
- **Misbruik**: bezoeker kan dure/grote URL's plakken of de fetch als gratis scraper misbruiken. Mitigatie:
  SSRF-guard (bestaat al voor logo-job — hergebruiken), 1 fetch hard, geen redirect-ketens, output-cap,
  en de gates uit §2 (Turnstile + daglimiet + weekcap).
- **Funnel**: sterkst van alle concepten — het concept ís de waardepropositie (de agent leest de graaf),
  alleen geminiaturiseerd. CTA leidt recht naar registratie/toegang-aanvraag.

### Concept B — "Vraag de gids één ding over de AI-wereld van NL/BE"
Eén ingedikte concierge-vraag zonder login: *"Wie in NL/BE werkt aan agent-evals?"* → de agent antwoordt
gegrond op de **publieke** slice van de graaf (alleen publiek-zichtbare profielen) + 2-3 kaartjes.

- **Wow**: laat de graaf + agency zien (de echte noordster), niet alleen een losse maker.
- **Kost/call**: tool-loop kan 2-4 turns lopen → duurder en variabeler dan A. Realistisch **€0,05–€0,15/call**;
  plan **€0,12**. De concierge leest DB (geen web), dus geen externe fetch-kost, maar meer output/turns.
- **Misbruik**: hoogste — een open chat-prompt is een gratis Opus-endpoint; prompt-injection / off-topic
  misbruik. Mitigatie: **harde 1 vraag per bezoeker**, system-prompt strak op-onderwerp, alleen publieke data
  als grounding (geen lek van besloten profielen), Turnstile vóór de call.
- **Funnel**: goed, maar de bezoeker krijgt al "het antwoord" → minder dwang om lid te worden dan A. Daarom B
  als **tweede** vraag ná A, of achter de toegang-gate.

### Concept C — "Laat AI een tool of onderwerp duiden" (sluit aan op subteam 3)
Bezoeker kiest/typt een AI-tool of -onderwerp; Opus geeft een korte, eerlijke duiding (wat het is, waar het
sterk/zwak in is) + "X leden in het netwerk gebruiken dit". Leunt op de tool-catalogus (`Tool`, `profile_tool`).

- **Wow**: redelijk — nuttig maar dichter bij "ChatGPT kan dit ook" dan A/B.
- **Kost/call**: geen web nodig als we op de catalogus duiden → **€0,02–€0,05/call** (goedkoopst). Plan **€0,05**.
- **Misbruik**: laag-midden — gesloten keuzelijst (tools uit de catalogus) beperkt vrije prompts sterk;
  vrij-tekst-onderwerp iets risicovoller.
- **Funnel**: midden — leidt naar "zie wie dit gebruikt" → ledengids-teaser → toegang.

### Concept D — "Wat zou jij hier kunnen halen?" (personalisatie-haak, geen losse call)
Géén nieuwe betaalde call: hergebruikt de **uitkomst van A**. Nadat A de URL heeft geduid, voegt dezelfde
respons een regel toe: *"Op basis hiervan: je zou hier X (een mede-maker), Y (vraag/aanbod) kunnen halen."*

- **Wow**: maakt A af tot een persoonlijke pitch. **Kost**: €0 extra (zelfde call). **Misbruik**: n.v.t.
- **Funnel**: dit ís de conversie-zin. **Aanbeveling: D is geen apart concept maar de slot-stap van A.**

### Verworpen als niet-lid-ervaring
- **Discovery/footprint voor niet-leden** — te duur (minuten Opus + web_search-loop, €0,30–€1+/run) en te
  traag voor een eerste indruk. Blijft strikt lid-only.
- **fal.ai cover-generatie voor niet-leden** — kost zonder funnel-waarde; een beeld overtuigt geen AI-maker.

**Lanceer-set**: **A (incl. D-slot)** als hoofd-voordeur. **C** als goedkoop tweede tasten. **B** pas ná de
toegang-gate of als bewust duurdere "proef de agent"-knop met eigen sub-limiet. Reden: A heeft de beste
wow÷kost÷misbruik-verhouding én de strakste funnel.

---

## 2. Kosten-governance-ontwerp (kern-eigenaarschap)

Doel: **gewone-bezoeker-spend < €50/week, wiskundig gegarandeerd, niet gehoopt.** Vier lagen, in
volgorde van een request: **identificeren → gate (cap-check) → call → boeken**.

### 2.1 Metering — waar tellen we op, en hoe slaan we het op
- **Telunit = geverifieerde sessie-bezoeker.** We tellen per `visitor_id`: een server-gezette,
  signed cookie (zelfde `SECRET_KEY`-mechaniek als de sessie). Eén `visitor_id` = één daglimiet-emmer.
  Reden: pure IP is achter de Tunnel waardeloos (één upstream-IP), en pure cookie is wisbaar. We combineren
  daarom **cookie (daglimiet-emmer) + Turnstile (mens-bewijs per call) + echte client-IP** (secundaire,
  grovere rem). De **globale weekcap** is identiteits-onafhankelijk en daardoor de échte garantie.
- **Echte client-IP**: lees `CF-Connecting-IP` (Cloudflare zet die altijd, en de Tunnel is de enige weg
  naar binnen → niet te spoofen door de bezoeker). Centraliseer in één helper `client_ip(request)` en
  vervang het naïeve `request.client.host` op de niet-lid-paden. **Voorwaarde voor alle per-IP-caps.**
- **Spend-opslag = één append-only tabel `ai_spend_log`** (zie §4). Elke betaalde niet-lid-call schrijft
  één rij **met de echte token-usage** uit `response.usage` (we lezen die nu nergens uit — dat moet erbij).
  Kosten worden per rij berekend uit input+output-tokens × modelprijs en als `cost_eur_micros` opgeslagen,
  zodat de prijs-aanname bevroren in de data zit en een latere prijswijziging oude rijen niet vervalst.
  Acties van ingelogde leden schrijven hier **niet** (apart, ongelimiteerd pad) → ze tellen niet mee in de €50.

### 2.2 Limieten — daglimiet + weekcap, met nette degradatie
Drie geneste remmen (env-config, geen hardcode — spiegelt `rate_limit_*` in `config.py`):

1. **Per-bezoeker daglimiet** — `visitor_ai_calls_per_day` (start **3**). Telt rijen in `ai_spend_log`
   voor dit `visitor_id` in een glijdend 24u-venster (rij-tel-patroon, exact als `_recent_count`).
2. **Per-IP daglimiet (grover vangnet)** — `visitor_ai_calls_per_ip_per_day` (start **20**). Vangt
   cookie-wissers; ruimer omdat één IP soms een heel kantoor is.
3. **Globale weekcap (de garantie)** — `visitor_ai_budget_eur_per_week` (= **€50**). Vóór élke betaalde
   niet-lid-call sommeren we `cost_eur_micros` over het lopende ISO-week-venster; ligt de som + de
   **geschatte** kost van deze call boven de cap → **geen call**. Dit is een harde gate, geen alert.
   We gebruiken een **conservatieve voorschat** (bovengrens-planningswaarde per concept, §3) zodat we de
   cap nooit overschrijden door een dure uitschieter; na de call corrigeren we met de echte usage.

**Nette degradatie (geen kale error).** Als een limiet raakt, rendert dezelfde kosmische `view` een
eerlijke, eenvoudige staat — geen 429-pagina:
- Daglimiet vol: *"Je hebt vandaag de gratis proef gebruikt. Leden doen dit onbeperkt — vraag toegang."*
- Weekcap vol: *"De gratis proef is deze week uitverkocht. Kom morgen terug, of word lid — dan werkt de
  agent onbeperkt voor je."* + de constellatie blijft staan, met de toegang-CTA prominent.
Toon eenvoudig en direct (styleguide §3: geen "je ster is verschenen"), maar volledig in identiteit. De lege
staat is een **funnel-moment**, geen fout.

### 2.3 Misbruik/bot-bescherming
- **Cloudflare Turnstile vóór elke betaalde call** (Cloudflare zit er al voor — dit is "gratis" infra).
  De widget levert een token; de server **valideert server-side** (`/turnstile/v0/siteverify`) vóór de
  Opus-call. Geen geldig token → geen call. Dit alleen al stopt het leeuwendeel van geautomatiseerd misbruik.
- **Caching van identieke prompts** — hash van (concept, genormaliseerde input-URL/onderwerp). Identieke
  prompt binnen TTL (bv. 24u) → geserveerd uit cache, **geen nieuwe call, telt niet tegen het budget**.
  Spaart kosten bij virale/herhaalde links en dempt een "spam dezelfde URL"-aanval naar nul marginale kost.
- **Rate-limit op de gratis call** bovenop de daglimiet: max 1 call per `visitor_id` per ~30s (anti-burst),
  zelfde rij-tel-mechaniek op een kort venster.
- **SSRF-guard op fetch-URL's** (concept A) — hergebruik de bestaande guard van de logo-job: geen interne
  IP's/loopback, geen niet-http(s), 1 fetch, geen redirect-keten, response-size-cap.
- **Output-cap & geen agent-loop** op het niet-lid-pad: `MAX_TOKENS` laag (~1500), `tool_choice` strak,
  geen pause-turn-loop → een enkele call kan nooit ontsporen in een dure keten.

### 2.4 Monitoring/alerting (low-op-last)
- **Admin-meter** (één kaart op het bestaande admin-dashboard): live "deze week: €X,XX / €50 · N calls ·
  M unieke bezoekers · top-concept". Eén query op `ai_spend_log`. Geen extra dienst, geen Grafana.
- **Telegram-ping bij drempels** — hergebruik het **bestaande Telegram-push-kanaal** (`@dewereldvanaibot`,
  rich messages bestaan al): bij **80%** van de weekcap één bericht *"Bezoeker-AI-budget op 80% (€40/€50)
  deze week"*, en bij **100%** *"Weekcap geraakt — niet-leden zien nu de proef-uitverkocht-staat."* De
  100%-ping is informatief; de **gate heeft de call dan al geweigerd** (geen geld weg). Geen e-mail
  (conform notificatie-policy: alleen magic-link mailt).
- **Geen real-time dashboard nodig** voor Richard om mee te leven — de gate beschermt autonoom; de ping is
  alleen situational awareness. Dit respecteert "minimale ping-overhead".

---

## 3. Kosten-rekensom (zodat de limieten kloppen)

Aannames: Opus 4.8, €4,65/1M input · €23,25/1M output. Web-fetch-pagina telt als input.

**Per-call-kost per concept (bovengrens-planningswaarde):**

| Concept | Input (incl. fetch) | Output | Kost/call (plan) |
|---|---|---|---|
| A — URL→mini-kaart | ~12k tok (fetch+system) | ~600 tok | **€0,08** |
| B — concierge-vraag (2-4 turns) | ~8k tok cumulatief | ~1,5k tok | **€0,12** |
| C — tool/onderwerp duiden | ~2k tok | ~600 tok | **€0,05** |

**Hoeveel calls past er in €50/week?**

| Bij kost/call | Calls/week tot €50 | Calls/dag (÷7) |
|---|---|---|
| €0,05 (C) | **1.000** | ~143 |
| €0,08 (A, aanbevolen) | **625** | ~89 |
| €0,12 (B) | **416** | ~59 |

**Hoeveel bezoekers is dat?** Bij daglimiet **3 calls/bezoeker** en concept A (€0,08):
- 625 calls/week ÷ 3 = **~208 "volle" bezoekers/week** die hun hele proef opmaken, óf
- als de gemiddelde bezoeker ~1,3 calls doet (de meesten proberen één URL): **~480 unieke
  bezoekers/week** passen binnen €50.

**Conclusie voor de limieten**: met A op €0,08 en daglimiet 3 is **€50 pas vol bij ~480 bezoekers/week**
(~70/dag). Dat is een gezonde marketing-ruimte voor een besloten community-launch; raakt het toch vol, dan
degradeert het netjes en is er nul kosten-uitloop. De getallen zijn **env-config** zodat Richard ze zonder
deploy kan bijstellen (daglimiet omlaag = meer unieke bezoekers binnen dezelfde €50). Voor B (€0,12) halveert
de capaciteit ruwweg — reden om B niet als gratis voordeur-default te zetten.

**Veiligheidsmarge**: omdat we vóór de call met de bovengrens-planningswaarde gaten en pas ná de call met de
**echte** (meestal lagere) usage corrigeren, ligt de werkelijke spend structureel **onder** €50 — de cap is
een plafond, niet een streefwaarde.

---

## 4. Datamodel + gate-logica (concreet)

### 4.1 Nieuw model `AiSpendLog` (SQLAlchemy 2.x, spiegelt bestaande modellen)
Nieuwe migratie **`0022_ai_spend_log.py`** (laatste is `0021`). Append-only; geen update.

```text
ai_spend_log
  id              PK
  visitor_id      str   index   # signed-cookie visitor, niet member_id
  ip              str   index   # CF-Connecting-IP (echte client)
  concept         enum  ('url_card' | 'concierge_q' | 'tool_explain')
  prompt_hash     str   index   # voor identieke-prompt-cache + dedup
  input_tokens    int
  output_tokens   int
  cost_eur_micros int          # bevroren kost: tokens × modelprijs, in micro-euro
  cache_hit       bool         # True = uit cache geserveerd, cost_eur_micros = 0
  created_at      datetime index  # glijdend venster voor dag/week-tellingen
```

Leden-acties schrijven hier **niet** — die lopen via het bestaande (ongelimiteerde) lid-pad. Zo blijft de
€50-telling per definitie alleen "gewone bezoekers".

### 4.2 Config (toevoegen aan `app/config.py`, env-overschrijfbaar)
```text
turnstile_site_key / turnstile_secret_key   # None → niet-lid-AI uit (veilige default)
visitor_ai_calls_per_day            = 3
visitor_ai_calls_per_ip_per_day     = 20
visitor_ai_budget_eur_per_week      = 50.0
visitor_ai_min_seconds_between_calls= 30
visitor_ai_prompt_cache_ttl_hours   = 24
```
**Veilige default**: zonder Turnstile-keys is het hele niet-lid-AI-pad **uit** (toont de toegang-CTA zonder
betaalde call). Geen sleutels = geen onbedoelde spend. Spiegelt hoe Telegram nu gegate is zonder token.

### 4.3 Gate-volgorde (één `visitor_ai_guard`, vóór élke betaalde niet-lid-call)
```text
1. Turnstile-token server-side valideren        → faalt? toon "even verifiëren" / CTA, geen call
2. anti-burst: < min_seconds sinds vorige call?  → ja? "even geduld", geen call
3. prompt_hash in cache (< TTL)?                 → ja? serveer cache, log cache_hit=True, €0
4. per-visitor daglimiet (rij-tel 24u)?          → vol? degradatie-staat "vandaag op", CTA
5. per-IP daglimiet (rij-tel 24u)?               → vol? degradatie-staat, CTA
6. GLOBALE WEEKCAP: som(cost) lopende week
     + voorschat(concept) > budget?              → over? degradatie-staat "deze week uitverkocht", CTA
7. → call uitvoeren (Opus, gecapt, SSRF-guard)
8. → response.usage uitlezen, cost berekenen, ai_spend_log-rij schrijven
9. → drempel-check: weekcap ≥80%/100% net gepasseerd? → Telegram-ping (idempotent per week)
```
Stappen 1-6 zijn **goedkoop** (cookie-check, een paar `COUNT`/`SUM`-queries) en draaien vóór elke dure call.
Stap 6 is de wiskundige garantie. Stap 8 maakt de telling zelf-corrigerend op echte kosten.

---

## 5. Fasering

- **Fase 1 — fundament (blokkerend voor alles)**: `client_ip()`-helper op `CF-Connecting-IP`;
  `AiSpendLog`-model + migratie 0022; config-vars; Turnstile server-side validatie; `visitor_ai_guard`.
  Zonder dit géén niet-lid-call live zetten.
- **Fase 2 — voordeur**: Concept **A** (URL→mini-kaart, incl. D-slot) als niet-lid-variant van
  `ai_profile` — ingedikt (1 fetch, gecapt, geen loop), publieke kosmische `view`, degradatie-staten,
  admin-meter + Telegram-drempel-ping.
- **Fase 3 — verbreden**: Concept **C** (goedkoop, catalogus-gegrond) als tweede knop. Caching-laag
  aanscherpen op echte verkeerspatronen.
- **Fase 4 — optioneel/duurder**: Concept **B** (concierge-proef) met **eigen, krappere** sub-limiet,
  of pas ná de toegang-gate. Alleen als de meter laat zien dat er budget-ruimte over is.

Elke fase: SemVer + CHANGELOG + `status.md`/`decisions.md`-bump conform werkwijze.

---

## 6. Aanbeveling + verworpen alternatieven + risico's

**Aanbeveling (PASS).** Bouw **Concept A** als publieke voordeur, gegate door **Turnstile + per-bezoeker
daglimiet (3) + harde globale weekcap (€50, pre-call) + identieke-prompt-cache**, met spend per call geboekt
in `ai_spend_log` op **echte token-usage**, een admin-meter, en een Telegram-ping bij 80%/100%. De weekcap is
een **harde gate vóór de call**, dus kosten-uitloop is wiskundig uitgesloten — passend bij "geen buffer".
Eerst Fase 1 (fundament), dan A. **Ik begin daarmee tenzij je vetoert.**

**Verworpen alternatieven (1 regel elk):**
- *Concept B als gratis voordeur* — duurder/variabeler per call én zwakkere funnel (geeft het antwoord al weg).
- *Discovery voor niet-leden* — minuten Opus + web_search-loop = €0,30–€1+/run; onbetaalbaar als open proef.
- *Alleen rate-limit zonder spend-cap* — limiteert frequentie maar niet euro's; één dure uitschieter kan de pot leegtrekken.
- *Pure IP-metering* — achter de Tunnel is dat één upstream-IP → blind; cookie+Turnstile+weekcap is de werkende combinatie.
- *Geen Turnstile* — laat een open Opus-endpoint achter dat bots gratis kunnen leegtrekken tot de weekcap.

**Risico's & mitigatie:**
1. **Cookie-wissen omzeilt daglimiet** → per-IP-vangnet + Turnstile (mens-kost per call) + **de weekcap die
   identiteit-onafhankelijk is**. De €50 staat hoe dan ook vast.
2. **Voorschat te laag → cap-overschrijding** → bewust **conservatieve bovengrens**-voorschat per concept;
   na-correctie op echte usage trekt de telling alleen maar omlaag.
3. **`CF-Connecting-IP` niet doorgezet** → faal veilig: ontbreekt de header, behandel als "onbekend IP" en
   leun op cookie+Turnstile+weekcap (de garantie blijft staan).
4. **Misbruik via grote/interne URL's (A)** → SSRF-guard hergebruiken, 1 fetch, response-size-cap, output-cap.
5. **Prompt-injection (B)** → B niet als gratis default; strak system-prompt, alleen publieke graaf-data als
   grounding, Turnstile vóór de call.
6. **Turnstile-keys ontbreken** → veilige default: niet-lid-AI-pad **uit**, toont CTA, nul spend.
```
