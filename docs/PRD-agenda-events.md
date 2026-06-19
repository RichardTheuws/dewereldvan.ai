# PRD — Agenda / Events: meetups die iedereen toevoegt

**Status:** 🟡 TER GOEDKEURING (2026-06-19) — wacht op akkoord/fork vóór bouw
**Versie-doel:** 0.24.0 (MINOR — nieuwe entiteit + pagina)
**Datum:** 2026-06-19
**Aanleiding (eigenaar):** een agenda met meetups — `aimelo.nl` erin, plus de (wekelijkse?) meetup
omgeving Meppel/Zwolle, met een **kaart per meetup en de frequentie duidelijk zichtbaar**. Het moet
**verbazen** (zoals elke pagina), en het moet **duidelijk zijn dat iedereen events mag toevoegen**.
Plus: de **andere roadmap-onderdelen** alvast wat cachet geven met voorbeelden.

---

## 0. Eén regel

Een nieuwe `Event`-entiteit + een kosmische **`/agenda`**-pagina met meetup-kaarten waarop de
**frequentie** (wekelijks/maandelijks/eenmalig…) prominent oplicht; elk ingelogd lid voegt vrij events
toe (in-stroom via de agent of via een open formulier), admin kan verbergen. Gegrond, holistisch
gemodelleerd, verweven in de agent-shell.

---

## 1. Datamodel — `Event` (holistisch, klein)

Spiegelt het `Idea`-patroon (lid-toegevoegd + admin-`hidden`-moderatie) met event-velden.

| Veld | Type | Opmerking |
|---|---|---|
| `id` | int PK | |
| `added_by_id` | FK member, **SET NULL**, nullable | Wie 'm toevoegde; **SET NULL** zodat een community-meetup blijft staan als de toevoeger zijn account wist (anders dan idee→CASCADE). Admin/seed mag `NULL`. |
| `title` | String(200) | "Aimelo — AI-meetup Almelo" |
| `description` | Text, nullable | |
| `location` | String(160), nullable | "Almelo" / "Meppel/Zwolle" / "online" |
| `url` | String(500), nullable | bv. `https://aimelo.nl` |
| `frequency` | enum `EventFrequency` | **eenmalig · wekelijks · tweewekelijks · maandelijks · doorlopend** — voedt de zichtbare badge |
| `next_at` | DateTime, nullable | eerstvolgende datum/tijd (eenmalig: dé datum; terugkerend: de volgende keer) |
| `cadence_note` | String(120), nullable | vrije, leesbare cadans bij terugkerend ("elke donderdag 19:00") |
| `hidden` | bool, default false, index | admin-moderatie (spiegelt `idea.hidden`) |
| `created_at` | DateTime server_default | |

**Recurrence — bewust simpel (aanbevolen):** een `frequency`-enum + `next_at` + vrije `cadence_note`.
GEEN volledige RRULE/iCal-machinerie (overkill, hoge op-last). De badge toont de frequentie; `next_at`
toont "eerstvolgende"; `cadence_note` geeft de menselijke uitleg. Verleden events (next_at < nu) bij een
terugkerend event blijven tonen met hun frequentie; eenmalige verlopen events kun je later filteren.

Eén Alembic-migratie. AVG: `Event` opnemen in `delete_member_completely` (alleen `added_by_id` nullen,
niet de rij wissen — community-waarde blijft).

---

## 2. De ervaring — `/agenda` (verbazen)

Kosmische pagina (login-gated, `noindex`; mag later publiek). Eén constellatie van **meetup-kaarten**:

- **Frequentie-badge prominent** op elke kaart (✦ WEKELIJKS / MAANDELIJKS / EENMALIG …) — kleur-gecodeerd
  (terugkerend = cyaan/levend, eenmalig = goud), zodat de cadans in één oogopslag leest.
- **Eerstvolgende** datum + relatieve tijd ("over 3 dagen") groot; locatie + link eronder; `cadence_note`
  als rustige regel ("elke donderdag 19:00").
- **Sorteren**: terugkerend + eerstvolgend bovenaan; gegrond op `next_at`.
- **"Iedereen voegt toe" is geen verstopt formuliertje:** een uitnodigende, altijd-zichtbare kaart/CTA
  ("✦ Ken jij een AI-meetup? Zet 'm in de agenda") — opent de toevoeg-flow. Lege staat = die uitnodiging
  groot, niet "nog geen events".
- Verweven met de agent: "wat is er te doen?" / "laat de agenda zien" → `surface(agenda)` in de canvas;
  "voeg een meetup toe: …" → `draft_event` (voorgevuld → bevestigen, zoals de andere schrijf-surfaces).

## 3. Iedereen voegt events toe

- **Open voor leden** (de community is besloten/ingelogd → geen anonieme spam). Direct zichtbaar na
  toevoegen (geen goedkeuringswachtrij — past bij "iedereen mag toevoegen"); admin kan een event
  **verbergen** (`hidden`, spiegelt idee-moderatie). Aanbevolen boven admin-vooraf-goedkeuren (dat zou
  "iedereen voegt toe" ondergraven).
- Twee toevoeg-paden, één endpoint/stramien: (a) het open formulier op `/agenda`, (b) de
  `draft_event`-agent-tool ("tonen + 1-klik bevestigen"). Beide → `POST /agenda` (Pydantic-schema +
  CSRF + rate-limit, zoals ideeën).

## 4. Seed-content (gegrond)

- **aimelo.nl** — ik haal `aimelo.nl` op met web_fetch voor de ECHTE details (locatie, frequentie,
  eerstvolgende datum) i.p.v. te gokken. Verzin geen frequentie.
- **Meetup Meppel/Zwolle** — toegevoegd met de door jou genoemde indicatie ("wekelijks?"); duidelijk
  als concept/te-verifiëren gemarkeerd zodat jij of de organisator 'm corrigeert (de frequentie-badge
  maakt een fout meteen zichtbaar). Heb je een naam/URL, dan vul ik die.

## 5. Roadmap-cachet (de andere onderdelen)

De `/roadmap` is nu leeg/dun. Ik seed 'm met **voorbeeld-roadmap-items** voor de echte onderdelen, met
verzorgde omschrijvingen + statussen (zodat de roadmap meteen substantie heeft):
- Ledengids & profielen (✓ klaar), AI-profielbouw (✓), Agent-canvas (✓), **Agenda/meetups (in aanbouw)**,
  Matchmaking vraag↔aanbod (gepland), Community/updates (overwegen), Publieke showcase (overwegen),
  Contact/intro's (overwegen).
Dit geeft de roadmap cachet zonder elk onderdeel nu vol te bouwen — het toont de richting.

## 6. Architectuur — hergebruik vs. nieuw
- **Hergebruik:** het idee-patroon (model + `POST`-endpoint + schema + rate-limit + admin-hide), de
  surface-machinerie + `draft_*`-tools (Fase 2), de cosmic-tokens + kaart-esthetiek, de footer/nav +
  instant-index + `surface_registry`.
- **Nieuw:** `Event`-model + migratie + `EventFrequency`-enum; `routers/agenda.py` (`GET /agenda`,
  `POST /agenda`, admin-hide); `event_service`; templates (`agenda/index.html` + `_event_card.html` +
  `_event_form.html`); `surface(agenda)`-loader + `draft_event`-tool; seed.

## 7. Edge cases & guardrails
| Risico | Mitigatie |
|---|---|
| **Spam/rommel** | Leden-only (login-gated) + admin-`hidden` + rate-limit (zoals ideeën). |
| **Verzonnen meetup-details** | aimelo.nl wordt gefetcht (gegrond); Meppel/Zwolle expliciet als te-verifiëren. |
| **Toevoeger wist account (AVG)** | `added_by_id` SET NULL → het event blijft (community-waarde); opgenomen in `delete_member_completely`. |
| **Verlopen events** | terugkerend blijft (frequentie); eenmalig-verlopen later wegfilteren (Fase 2). |
| **"verbazen"-mandaat** | frequentie-badge + eerstvolgende-countdown + levende kosmische kaarten; geen kaal lijstje. |

## 8. Fasering
- **Fase 1 (v0.24.0):** `Event`-model + migratie + `/agenda`-pagina (kaarten + frequentie-badge +
  open toevoeg-flow + "iedereen voegt toe"-CTA) + seed (aimelo gefetcht, Meppel/Zwolle) + nav/footer +
  roadmap-cachet-seed. Tests.
- **Fase 2 (na akkoord):** `surface(agenda)` + `draft_event`-agent-tool (in-canvas toevoegen), verlopen-
  filter, evt. publiek maken.

---

## 9. Open vraag (echte keuze — aanbeveling)

**Toevoegen door leden: direct zichtbaar (open) of eerst admin-goedkeuren?**
- **(A) (Aanbevolen)** Direct zichtbaar + admin kan verbergen (spiegelt ideeën). Maakt "iedereen voegt
  toe" echt; besloten community + rate-limit + hide dekt misbruik.
- **(B)** Admin keurt elk event vooraf goed. Veiliger tegen rommel, maar ondergraaft "iedereen voegt
  vrij toe" en geeft jou doorlopende op-last.

*Aanbeveling A. Verder begin ik met Fase 1 (model simpel: frequency-enum + next_at + cadence_note, géén
RRULE) zodra je akkoord bent — tenzij je vetoert of de fork bijstelt.*
