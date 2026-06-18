# PRD — Schrijf-surfaces: de agent voert ledenacties uit ("tonen + 1-klik bevestigen")

**Status:** 🟡 TER GOEDKEURING (2026-06-19) — wacht op akkoord + fork-keuze vóór bouw
**Versie-doel:** 0.18.0 (MINOR — nieuwe feature, additief op de Agent-Shell)
**Datum:** 2026-06-19
**Bouwt voort op:** [PRD-agent-shell.md](PRD-agent-shell.md) (Fase 1 live) +
[PRD-conversationele-profielbouw.md](PRD-conversationele-profielbouw.md) (variant A live).

> **Eigenaar-eis (oorspronkelijk):** "aan de ledenkant moet de agent ook daadwerkelijk acties uit kunnen
> voeren, volgens een **gezet stramien per entiteit** om wildgroei te voorkomen."
> **Beslist schrijf-model (Agent-Shell fork, 2026-06-18):** **tonen + 1-klik bevestigen** — de agent
> stelt voor en vult voor; het lid bevestigt elke schrijf-actie zelf; alleen het bestaande
> CSRF-/consent-/rate-limit-bewaakte endpoint commit.

---

## 0. Eén regel

De agent kan ledenacties **voorbereiden** maar nooit zelfstandig wegschrijven: hij rendert het échte,
voorgevulde formulier in de stroom (een **draft-surface**), het lid bevestigt met één klik, en de
bestaande mutatie-endpoint commit. Eén schrijf-pad, één validatie-stramien per entiteit, geen tweede
AVG-poort.

---

## 1. Het mechanisme (de harde regel)

```
agent → draft_<entiteit>(velden?)        # tool: valideert + geeft een {entity, fields}-signaal
router → render het VOORGEVULDE echte formulier als surface in de stroom
lid    → past evt. aan + klikt "bevestig"
form   → POST naar het BESTAANDE endpoint (CSRF + Pydantic-schema + rate-limit) → commit
router → het resultaat-fragment materialiseert in de stroom (de echte rij/kaart)
```

- **De draft-tool schrijft NIET.** Hij geeft alleen een gevalideerd `{entity, fields}`-signaal terug
  (zoals `surface` een `{view, params}`-signaal geeft). De router rendert het bestaande edit-fragment,
  **voorgevuld** met de door de agent voorgestelde waarden.
- **Het bestaande endpoint commit.** `POST /profiel/offering`, `POST /profiel/need`, `POST /ideeen` —
  ongewijzigd, met hun Pydantic-schema + CSRF + rate-limit. Dat schema-per-entiteit *is* het "gezet
  stramien om wildgroei te voorkomen".
- **Grounding voor schrijven ≠ grounding voor lezen.** Bij lezen mag verzonnen data NOOIT renderen
  (harde poort). Bij schrijven mág de agent waarden VOORSTELLEN — want het lid ziet ze in een
  bewerkbaar formulier en is de poort: niets wordt opgeslagen tot de bevestig-klik. De klik is de
  grounding.

---

## 2. Per-entiteit (de vaste DRAFT_REGISTRY)

Net als `SURFACE_REGISTRY` is er een **vaste** `DRAFT_REGISTRY` — de agent kan alleen geregistreerde
entiteiten draften, geen vrije writes.

| Draft-tool | Voorgevulde velden | Bestaand commit-endpoint | Schema |
|---|---|---|---|
| `draft_offering` | `title` (≤160), `description?` (≤4000) | `POST /profiel/offering` | `OfferingForm` |
| `draft_need` | `title` (≤160), `description?` | `POST /profiel/need` | `NeedForm` |
| `draft_idea` | `title`, `body` | `POST /ideeen` (rate-limit) | `IdeaForm` |

**Complementair aan de profielbouw (Fase 1):** de `profile_builder`-surface bouwt het profiel in bulk
uit een scan/verhaal; de draft-tools zijn de **incrementele, conversationele** toevoegingen dáárna
("voeg dit project toe", "ik zoek ook iemand voor X") → tonen + bevestigen.

**Buiten scope (bewust — gevoelig/AVG):** zichtbaarheid → openbaar (`VisibilityForm` + `consent`) en
profiel-verwijdering houden hun **eigen, dedicated consent-flow**. De agent mag erheen *wijzen*
("dat regel je hier"), maar levert er GEEN draft-commit voor. Eén AVG-poort, niet via de agent te omzeilen.

---

## 3. De ervaring (microcopy, eenvoudig)

> jij: *voeg een project toe: een AI-assistent voor de zorg*
> ✦ de gids
> ✦ Ik heb dit alvast ingevuld — klopt het? Pas gerust aan.
> ┌─ Wat ik maak ─────────────────────────────┐
> │ Titel: [AI-assistent voor de zorg        ] │
> │ Beschrijving: [ … voorgevuld … ]           │
> │            [ ✦ Toevoegen ]   ✕ laat maar    │
> └────────────────────────────────────────────┘

Na "Toevoegen": het echte offering-kaartje materialiseert in de stroom (en in het profiel). "Laat maar"
sluit het concept zonder iets op te slaan. Eenvoudige, directe taal — geen "je ster is toegevoegd".

---

## 4. Architectuur — hergebruik vs. nieuw

### 4.1 Hergebruikt 1:1
- De **mutatie-endpoints + Pydantic-schemas** (`OfferingForm`/`NeedForm`/`IdeaForm`) + hun CSRF-,
  rate-limit- en consent-discipline. Geen tweede schrijf-pad.
- De bestaande **edit-/rij-partials** (`profiles/_offering_need_row.html`-editvorm, `ideas/_form.html`)
  — we renderen ze voorgevuld.
- De **surface-machinerie** (Fase 1): tool-signaal → router rendert in-stroom in een eigen `SessionLocal`.
- De **canvas-stream + verse-proxy-bind** + de `concierge_turn`-state.

### 4.2 Nieuw (klein, afgebakend)
- `concierge_service`: `draft_offering`/`draft_need`/`draft_idea`-tools + `DRAFT_REGISTRY`
  (entity → toegestane velden, str-whitelist zoals `tool_surface`). Een `on_draft`-callback (spiegelt
  `on_surface`). De tools schrijven niets.
- `routers/concierge`: render-poort voor het voorgevulde formulier (een `draft`-SSE-event, of hergebruik
  het `surface`-event met een `draft`-view-variant); de form-partial post naar het bestaande endpoint;
  op succes materialiseert het resultaat-fragment in de stroom.
- Partials: dunne voorgevulde wrappers om de bestaande edit-forms (één per entiteit), met de
  `[ bevestig ] ✕ laat maar`-actie. cosmic.css-tokens, geen tweede palette.
- System-prompt: leer de agent wanneer te draften ("voeg toe", "ik zoek", "idee:") en dat hij waarden
  VOORSTELT maar het lid laat bevestigen.

---

## 5. Edge cases & guardrails
| Risico | Mitigatie (hard) |
|---|---|
| **Ongewenste/auto-write** | Geen tool schrijft; alleen het bestaande endpoint commit ná de bevestig-klik. |
| **Wildgroei** | Vaste `DRAFT_REGISTRY` + per-entiteit Pydantic-schema (lengtes, verplichte velden). Geen vrije entiteiten/velden. |
| **AVG / gevoelige acties** | Zichtbaarheid-openbaar + verwijdering blijven dedicated (consent-poort); de agent draft ze NIET. Eén AVG-poort. |
| **Hallucinatie bij schrijven** | De agent stélt voor; het lid ziet + bewerkt + bevestigt. Niets wordt opgeslagen zonder klik. Verzonnen velden zijn zichtbaar en corrigeerbaar vóór commit. |
| **Prompt-injectie via profieltekst** | Bestaande guard (tool-data/profieltekst = gegevens, geen instructies). |
| **Rate-limit / spam** | De bestaande endpoint-rate-limits (idee, enrich) blijven gelden. |
| **CSRF** | De voorgevulde form erft de canvas-`hx-headers`-CSRF; het endpoint valideert zoals nu. |
| **Anon** | Draft-tools vereisen een ingelogd lid (de canvas is sowieso login-gated). |

---

## 6. Fasering + succescriterium

### Fase 2.1 — Constructieve writes (v0.18.0)
1. `DRAFT_REGISTRY` + `draft_offering`/`draft_need`/`draft_idea`-tools (geen write) + `on_draft`.
2. Render-poort: voorgevuld formulier in-stroom; commit via het bestaande endpoint; resultaat
   materialiseert.
3. Voorgevulde form-partials (3) met `[ bevestig ] ✕ laat maar`.
4. System-prompt-uitbreiding (wanneer draften; voorstellen-niet-opslaan).
5. Tests (registry-grens, geen-write-zonder-klik, schema-validatie via het echte endpoint, AVG: geen
   visibility/delete-draft, anon geweigerd) + CHANGELOG.

### Fase 2.2 — Verrijking (na akkoord)
- Profiel-tekstvelden draften vanuit de conversatie (`headline`/`bio`/`seeking` → `PATCH /profiel/ai/veld`).
- Tag-suggesties ("zal ik 'voice-agents' toevoegen?").
- "Stel me voor"-introductie als lichte schrijf-actie (bericht/markering), als de community dat wil.

### Succescriterium (PASS/FAIL — eigenaar-oordeel)
Een lid zegt in de canvas "voeg een project toe: …", ziet een **voorgevuld** formulier verschijnen,
past één woord aan, klikt **bevestig**, en het echte projectkaartje materialiseert — zonder ooit een
los formulier op te zoeken, en zonder dat er iets is opgeslagen vóór de klik. Gevoelige acties
(openbaar maken, verwijderen) lopen nog steeds uitsluitend via hun eigen bevestigde flow.

---

## 7. Open vraag voor de eigenaar (echte keuze — aanbeveling)

**Scope van Fase 2.1: welke entiteiten laten we de agent draften?**

- **(A) (Aanbevolen)** Alleen **constructief**: `offering`, `need`, `idea`. Zichtbaarheid-openbaar en
  verwijdering blijven dedicated (consent-poort), buiten de agent. Maximale waarde (matchmaking-velden +
  ideeën) met de laagste AVG-/risico-oppervlakte.
- **(B) Inclusief zichtbaarheid-toggle** via een draft die de bestaande consent-poort toont (de agent
  bereidt voor, het lid vinkt consent + bevestigt). Iets meer gemak, maar brengt een gevoelige AVG-actie
  binnen het agent-oppervlak — meer zorg nodig.

*Aanbeveling A: houd de eerste schrijf-laag puur constructief en privacy-veilig; breng zichtbaarheid
pas later in als A in de praktijk goed voelt. Verwijderen blijft sowieso dedicated.*

---

*Ik begin met Fase 2.1 (variant A, tenzij je B kiest) zodra dit is goedgekeurd — tenzij je vetoert of de
fork bijstelt.*
