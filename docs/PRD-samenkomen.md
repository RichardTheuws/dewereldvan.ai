# PRD — Samenkomen (datumprikker + Dichtbij)

**Status**: DRAFT — wacht op goedkeuring
**Datum**: 2026-07-10
**Relatie**: `PRD-agenda-events.md` (event-`Post` + RSVP + AI-curatie), `PRD-matchmaking.md`
(`match_service`), `PRD-concierge-intelligentie.md` (agent-shell, nudges, `surface`/`connect`),
`PRD-discovery.md` (`graph_service` interesse-graaf), `PRD-notificaties.md` (lid-gekozen kanaal),
`docs/STYLEGUIDE.md` (kosmische diepte, één look).

---

## 1. Aanleiding & kern-inzicht

Leden vragen om drie dingen in het besloten deel: **elkaar makkelijker vinden en benaderen**,
**meer van elkaars werk zien**, en **fysiek samenkomen**. De rode draad is niet "meer features"
maar **minder wrijving om van online-nabijheid naar een echte ontmoeting te komen**.

Kern-inzicht uit de codebase-audit (2026-07-10): het platform heeft de bouwstenen al, ze staan
alleen niet in dienst van "samenkomen":

- De **Concierge agent-shell** is de woonkamer van een lid (`/` → `concierge/_canvas.html`,
  `app/main.py:291`). De agent heeft al `connect`, `surface` (o.a. `agenda`, `matches`,
  `connections`) en `draft_event`. Elke nieuwe interactie hoort hiér te leven, niet als losse pagina.
- Er is al een **interesse-graaf**: `graph_service` (`app/services/graph_service.py`) weet wie
  dezelfde tools/tags deelt ("beiden in voice-agents"). Daarmee kan "auto-selectie van
  geïnteresseerden" **vandaag al**, volledig zonder locatie. 50 km is een *verfijning*, geen kern.
- **Agenda + RSVP + AI-curatie** draaien (`Post` kind=event met enkelvoudige `next_at`,
  `EventAttendance`, `event_curation_service`).
- De **race-veilige stem-truc** (`idea_service.vote()` met `db.begin_nested()`-savepoint,
  `app/services/idea_service.py:250`) en de **htmx-RSVP-strip** (`agenda/_rsvp.html` +
  `_rsvp_strip`, `app/routers/posts.py:212`) zijn kant-en-klaar te kopiëren.

Wat ontbreekt: (a) een datumprikker (nul multi-datum/poll — `next_at` is enkelvoudig),
(b) per-lid locatie (nul locatiedata, nul geo-libs, zichtbaarheid is binair members/public),
(c) een lichte, wrijvingsloze contact-zet.

## 2. Doel

1. **Een lid kan met één zin een samenkomst starten** en de agent regelt de coördinatie: kandidaat-
   datums prikken, de juiste mensen erbij oppervlakken, stemmen verzamelen, en de winnaar omzetten
   in een echt agenda-event.
2. **"Auto-selectie van geïnteresseerden"** werkt eerst op de interesse-graaf (gedeelde tools/tags),
   later verfijnd met **grof + opt-in** locatie ("~40 km").
3. **Contact wordt lichter, niet zwaarder**: de bestaande privacy-veilige intro→accept→e-mail blijft,
   maar de agent stelt de intro voor en verstuurt 'm in één klik — geen inbox om te beheren.
4. **Lage op-last**: hergebruik van event-model, RSVP-patroon, vote-savepoint en de concierge; geen
   nieuwe infra, geen JS-buildpipeline, geen betaalde AI voor anonieme bezoekers.

## 3. Ervaring

### 3.1 Fase 1 — De datumprikker als concierge-act *(nu bouwbaar, géén beleidshorde)*

Een lid zegt in de shell: *"Ik wil een keer offline afspreken met mensen die met voice-agents bezig
zijn."* De Concierge:

1. **Stelt een samenkomst voor** (`draft_gathering`, uitbreiding van `draft_event`): titel, korte
   omschrijving, plek-suggestie (vrije tekst), en **3–5 kandidaat-datums** (slimme voorstellen:
   doordeweekse avonden + een weekenddag, weken vooruit).
2. **Oppervlakt de juiste mensen** via de interesse-graaf: *"Deze 6 leden werken ook met voice-agents
   — meenemen in de uitnodiging?"* (`graph_service.related_members`, gefilterd op de tag/tool uit de
   vraag). Dit is de "auto-selectie" — zonder geo.
3. **Publiceert de prikker.** Uitgenodigde leden krijgen een seintje via hun **gekozen kanaal**
   (in-app chip default, Telegram push opt-in — `notification_service.notify`, nooit e-mail).
4. **Verzamelt stemmen.** Per lid, per datum-optie: **ja / misschien / nee** (htmx-strip in de stijl
   van `_rsvp.html`; race-veilig via savepoint-upsert, `idea_service.vote()`-recept).
5. **Wint een datum → de prikker klapt samen tot een gewoon agenda-event**: er wordt een `Post`
   kind=event aangemaakt met `next_at` = winnende datum, en de "ja"-stemmers worden `EventAttendance`
   attending. Vanaf hier nemen de bestaande RSVP-, agenda- en curatie-flows het over. **Nul nieuwe
   event-infra downstream.**

**Kosmische behandeling (verplicht, geen kaal formulier):** de kandidaat-datums zijn sterren in een
kleine constellatie; naarmate stemmen binnenkomen lichten ze op (helderheid ∝ ja-stemmen), de
winnende datum "ontbrandt" bij het samenklappen. Heldere, gewone taal in de microcopy
("Wanneer kun jij?", "3 mensen kunnen op deze avond"), kosmisch in het beeld — conform het mandaat.

### 3.2 Fase 2 — "Dichtbij" (grof + opt-in locatie) *(na fundament + één migratie)*

Bovenop de interesse-graaf komt een **afstandsfilter**: "geïnteresseerd én dichtbij". Beleidskeuze
vastgelegd (2026-07-10): **grof + opt-in**.

- Een lid kan **optioneel** een **grof gebied** opgeven — postcode-**gebied** (eerste 2 cijfers, bv.
  `35xx`) of gemeente. **Nooit** een exact adres, huisnummer of straat. Default: **uit** (geen locatie).
- Bij opgave wordt éénmalig het middelpunt van dat gebied naar lat/lng herleid (statische PC2→coord-
  tabel in de repo — geen externe geocoding-call, nul afhankelijkheid, nul PII naar derden).
- De agent verrijkt de auto-selectie: *"…en 3 daarvan zitten binnen ~40 km van jou."* Afstand wordt
  **grof** getoond (banden: "<25 km", "~25–50 km"), nooit als exacte km of coördinaat.
- Radius is een verfijning, geen harde eis: leden zónder locatie blijven volledig meedoen via de
  interesse-graaf. "Dichtbij" degradeert netjes.

### 3.3 Doorlopend — "Nieuw werk deze week" *(klein, ambient)*

Om "meer van elkaars werk zien" te vervullen zonder een nieuw tabblad: de Concierge oppervlakt
periodiek een **klein lint van nieuw werk** van leden die qua interesse-graaf bij je passen
(`surface` met een nieuwe view `recent_work`, gevoed door recente `Offering`s van publieke profielen).
Passief en warm, geen verplicht scherm.

## 4. Contact lichter *(gekozen richting: via de agent)*

Geen DM-inbox, geen chat. Het bestaande `Connection`-mechanisme (intro→accept→e-mail-onthulling,
`connection_service.py`) blijft de poort. De verandering is puur wrijving weghalen:

- Overal waar de agent een maker oppervlakt (auto-selectie, related_members, matches) biedt hij een
  **één-klik "Stuur een kort bericht"** aan; de Concierge stelt de intro-tekst voor (hergebruik
  `_suggested_message`) en `POST /intro?naar={slug}` verstuurt 'm (bestaand pad, `connections.py:110`).
- De ontvanger accepteert/wijst af via de bestaande chip (`chip_intros`); pas ná accept komt e-mail
  vrij (`can_view_contact`, ongewijzigd). Rate-limit ongewijzigd.

Netto: "makkelijk contact" = nul nieuwe surfaces, alleen de agent die de intro voorkauwt en verstuurt.

## 5. Datamodel

Nieuw (fase 1):

- **`Gathering`** (de prikker) — `id`, `creator_member_id` (FK), `title`, `description`,
  `location_hint: str|None` (vrije tekst), `interest_tag`/`interest_tool: str|None` (waarop de
  auto-selectie draaide, voor label), `state` (`open` → `resolved` → `cancelled`), `resolved_post_id`
  (FK→`Post`, gezet bij samenklappen), `created_at`, `closes_at: datetime|None`.
- **`GatheringDate`** — `id`, `gathering_id` (FK, CASCADE), `starts_at: datetime`, `position`.
- **`GatheringVote`** — `id`, `gathering_date_id` (FK, CASCADE), `member_id` (FK, CASCADE),
  `choice` (`yes`/`maybe`/`no`), `created_at`. **`UniqueConstraint(gathering_date_id, member_id)`**
  → race-veilige upsert via savepoint (recept: `idea_service.vote()`).
- **`GatheringInvite`** — `id`, `gathering_id` (FK), `member_id` (FK), `created_at`. Wie is
  uitgenodigd (voor het seintje + "jij bent uitgenodigd"-chip). Optioneel in fase 1: bij een open
  prikker mag elk lid dat 'm ziet stemmen; invites sturen alleen het seintje.

Nieuw (fase 2):

- Kolommen op **`Profile`** (of `Member`): `area_code: str(4)|None` (PC2, bv. `35`), `area_label:
  str|None` (weergavenaam, bv. "Utrecht e.o."), `area_lat`/`area_lng: float|None` (afgeleid,
  middelpunt). Default `None` (opt-in). Geen nieuwe `Visibility`-waarde; locatie is een apart,
  standaard-leeg opt-in-veld dat losstaat van members/public.
- Statische **PC2→coördinaat**-tabel in de repo (`app/data/pc2_centroids.json` o.i.d.), haversine in
  pure Python (nul nieuwe dependency).

## 6. Privacy & AVG

- **Locatie is strikt opt-in en grof** (PC2/gemeente, nooit adres). Default uit. Afstand alleen in
  banden getoond, nooit exact of als coördinaat.
- Locatie erft de zichtbaarheids-poort: alleen leden die zelf `visibility=public`/zichtbaar zijn en
  locatie hebben aangezet, tellen mee in "Dichtbij". Besloten profielen worden nooit op afstand
  vindbaar (poort: `members_service.list_public_profiles` / `visibility.py`, ongewijzigd).
- Geo blijft **on-platform**: statische centroïde-tabel in de repo, geen externe geocoding-call,
  geen PII naar derden.
- Eén-klik-wis (bestaand AVG-mandaat) verwijdert locatie + votes + gatherings mee (CASCADE).

## 7. Edge cases

1. **Dubbel stemmen / dubbel-submit** op dezelfde datum-optie → savepoint vangt `IntegrityError` op
   `uq_gathering_vote`, update de keuze i.p.v. tweede rij (geen 500, geen dubbeltelling). Verplicht:
   het pysqlite-savepoint-recept in `conftest.py` (zie idempotent-race learning).
2. **Gelijkstand** bij samenklappen → niet automatisch samenklappen; de agent legt de knoop bij de
   maker ("twee avonden even populair — welke wordt het?"). Nooit stil een winnaar kiezen.
3. **Prikker met nul stemmen** bij `closes_at` → agent seint de maker ("nog geen respons — verlengen,
   andere datums, of annuleren?"). Geen event aanmaken.
4. **Uitgenodigd lid trekt zich terug** / verwijdert account → CASCADE ruimt votes/invites; telling
   herberekent.
5. **Maker annuleert** een `open` prikker → `state=cancelled`, uitgenodigden krijgen één seintje.
   Al `resolved` (event bestaat al) → annuleren loopt via het bestaande agenda-event, niet de prikker.
6. **Auto-selectie levert nul makers** (nieuwe/nichetag) → agent valt terug op een open prikker
   ("nog niemand met precies die tag — ik zet 'm open voor iedereen die 'm ziet").
7. **Lid zonder locatie** in fase 2 → volwaardig deelnemer via interesse-graaf; "Dichtbij" toont 'm
   niet als afstand maar sluit 'm niet uit.
8. **Anonieme/pending bezoeker** ziet een prikker-link → geen stem, wel "word lid"-poort (zoals de
   RSVP-strip nu voor anon doet).
9. **Datum in het verleden** bij samenklappen (trage besluitvorming) → agent weigert en vraagt nieuwe
   datums (dezelfde datum-discipline als de agenda).
10. **Spam-prikkers** → rate-limit op aanmaken per lid (patroon: `check_intro_rate_limit`).

## 8. Fasering & niet-nu

- **Fase 1** (deze PRD, eerst): `Gathering`-model + migratie, stem-strip (htmx, savepoint),
  `draft_gathering` + auto-selectie via `graph_service`, samenklappen→event, seintjes via bestaand
  kanaal, één-klik-intro. Volledig zonder locatie. **Success**: een lid start via de agent een prikker,
  ≥1 ander lid stemt, een datum wint en verschijnt als echt agenda-event met de ja-stemmers als RSVP —
  geverifieerd in de **browser** (niet alleen tests).
- **Fase 2** (na fase 1 live): locatie-opt-in-veld + PC2-tabel + haversine + "Dichtbij"-verfijning in
  de auto-selectie. **Success**: een lid met opt-in-gebied ziet in de auto-selectie een grove
  afstandsband; een lid zonder locatie doet volwaardig mee.
- **Niet nu (expliciet afgewezen):** volwaardige DM/chat-inbox (moderatie + op-last botst met het
  lage-op-last-mandaat); exact-adres of straat-niveau locatie; externe geocoding-service; een losse
  Doodle-achtige datumprikker-pagina buiten de concierge (kaal formulier = regressie per mandaat).

## 9. Succescriteria (samengevat)

- Een samenkomst starten kost één zin tegen de agent; coördinatie (datums, mensen, stemmen, event)
  gebeurt in de shell, niet in losse schermen.
- "Auto-selectie" werkt vanaf dag één op interesse (graaf), met locatie als latere, opt-in verfijning.
- Contact is lichter geworden zónder nieuwe inbox: de agent kauwt de intro voor en verstuurt 'm.
- Elk oppervlak volgt `docs/STYLEGUIDE.md` (kosmisch beeld, gewone taal) — geen kaal formulier.
