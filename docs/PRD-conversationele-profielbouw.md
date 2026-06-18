# PRD — Conversationele profielbouw + first-run walkthrough

**Status:** 🟡 TER GOEDKEURING (2026-06-19) — wacht op akkoord + fork-keuze vóór bouw
**Versie-doel:** 0.16.0 (MINOR — nieuwe feature, additief op de Agent-Shell)
**Datum:** 2026-06-19
**Bouwt voort op:** [PRD-agent-shell.md](PRD-agent-shell.md) (Fase 1 live, v0.15.x) +
[PRD-ai-profiel.md](PRD-ai-profiel.md) (de bestaande levende profielbouw).

> **Aanleiding (eigenaar, 2026-06-19):** eerste reacties op de profielbouw waren **vol onbegrip —
> "mensen denken dat het veel werk is"**. Er moet een **demo/walkthrough** komen om gebruikers te
> begeleiden. De agent-shell is de hefboom om profielbouw van "een formulier invullen" naar "een
> gesprek van 2 minuten" te brengen.

---

## 0. Eén regel

Profielbouw mag niet voelen als werk. We brengen het **in de canvas-conversatie** (de agent interviewt,
het profiel materialiseert in-stroom terwijl je vertelt), zetten **progressive disclosure** in (geen
lege skeleton + beheer-secties vooraf), en geven een **first-run walkthrough** die een nieuw lid bij de
hand neemt. Hergebruik van de bestaande live-materialisatie-engine — geen tweede engine.

---

## 1. De diagnose (waarom het "veel werk" voelt)

De profielbouw (`/profiel/ai/bouwen` → `ai/live.html`) is al AI-gedreven en materialiseert live. Tóch
leest het als werk, om drie redenen:

1. **Alles staat er meteen.** Een nieuw lid ziet direct de héle lege profiel-skeleton
   (`ai/_live_form.html`: headline, bio, rollen, projecten, "wat je zoekt", tags) **plus** een
   publiceer-dok, een "opnieuw beginnen"-form en een "wis mijn profiel volledig"-sectie. Zes lege velden
   + drie beheerblokken = "ik moet dit allemaal invullen", ook al doet de AI het.
2. **Het is een aparte pagina die de canvas verlaat.** Een approved lid landt nu in de levende canvas;
   de "maak je profiel af"-chip navigeert wég naar een drukke, formulier-achtige pagina met eigen nav.
   De breuk in ervaring versterkt het "nu begint het werk"-gevoel.
3. **Geen begeleiding bij de eerste keer.** Niemand laat zien hoe wéinig moeite het kost. Je staat voor
   een veld en moet het zelf bedenken.

**De copy is al goed** (`/welkom`: "De AI bouwt je profiel; jij verfijnt het. Klaar in een paar
minuten."). Het probleem is niet de belofte — het is wat je vervolgens ziet.

---

## 2. De aanpak (drie ingrepen)

### 2.1 Profielbouw ín de canvas-conversatie
In plaats van wegnavigeren naar een formulier: de maker vertelt **in het canvas-veld** wie hij is en wat
hij maakt, en het profiel **materialiseert in-stroom** — veld voor veld, met dezelfde live-
materialisatie-esthetiek die nu al in `ai_profile` zit. Het voelt alsof de Ai het bouwt terwijl je
praat, niet alsof jij een formulier vult.

- Hergebruik **1:1 de `ai_profile`-materialisatie-engine** (`_materialize_stream.html`'s per-veld
  `f-*`-proxy-swaps + `routers/ai_profile.py` SSE) — die werkt al en lost de "live materialiseren"-
  belofte in. We ontsluiten 'm als een **canvas-surface** (`profile_builder`), zodat de profielvorm in
  de canvas-stroom verschijnt i.p.v. op een aparte pagina.
- **Progressive disclosure:** toon alleen wat al gematerialiseerd is. Lege velden tonen we niet als een
  invul-skeleton maar als een rustige "nog te ontdekken"-hint die de agent zelf aanstipt
  ("Zal ik er ook bij zetten wat je zoekt?").

### 2.2 First-run walkthrough (begeleiding)
Bij de **eerste** keer dat een goedgekeurd lid de canvas opent (één keer, zoals de founder-welkomst —
de bewuste uitzondering op "geen autonome pop-up"), biedt de agent zich proactief aan:

> ✦ Welkom, {voornaam}. Zal ik je profiel opbouwen? Vertel in één of twee zinnen wie je bent en wat je
> maakt — plak gerust een link. Ik doe de rest; jij verfijnt.
> [ Ja, bouw mee ]   ✕ later

`[Ja, bouw mee]` zet de cursor in het veld met een voorbeeld-placeholder. Daarnaast een **lichte
walkthrough** (2-3 voorbeeld-vragen als chips) zodat niemand voor een leeg veld zit: *"wie bouwt hier
voice-agents?"*, *"laat de roadmap zien"*, *"bouw mijn profiel"*. Dismissbaar, één keer.

### 2.3 Agent-response-tuning (de canvas voelt slim)
Live waargenomen (v0.15.1): op "laat de makers zien" vroeg de agent eerst om een filter én toonde tóch
een kaart — tegenstrijdig. **System-prompt-aanscherping:** een brede "toon"-intent (`laat de makers
zien`, `wie zijn de leden`) → `surface(members_grid)` **zonder** een filter te eisen (toon iedereen);
alleen bij een specifieke zoekvraag een filter. Vergelijkbaar: "laat de roadmap zien" → `surface
(roadmap_board)` direct. Geen "ik kan niet zonder…"-antwoorden op brede toon-intents.

---

## 3. Hergebruik vs. nieuw

### 3.1 Hergebruikt 1:1
- De **`ai_profile`-materialisatie-engine** (`ai_conversation` + `routers/ai_profile.py` +
  `_materialize_stream.html` per-veld `f-*`-proxy's) — de bewezen live-profiel-opbouw.
- De **profiel-mutatie-endpoints** + consent-/publiceer-poort (niets publiek tot expliciete bevestiging
  — AVG-grens blijft hard).
- De **canvas-surface-machinerie** (Agent-Shell Fase 1) + de nudge/chip-laag (pure SQL).
- De goede **onboarding-copy** (`/welkom`).

### 3.2 Nieuw (afgebakend)
- Een `profile_builder`-surface die de levende profielvorm in de canvas-stroom host (brug tussen de
  `ai_profile`-SSE en de canvas-host).
- First-run-trigger (één-malig, sessie/DB-flag zoals `founder_welcome`) + de walkthrough-chips.
- System-prompt-aanscherping voor brede toon-intents (geen datamodel-wijziging).
- Progressive-disclosure-variant van `_live_form.html` (lege velden = rustige hint i.p.v. invul-skeleton).
- **Geen** verplaatsing/sloop van `/profiel/ai/bouwen` zelf: die blijft bestaan als volwaardige
  bewerk-pagina (deep-link, herlaad-idempotent); de canvas wordt de *primaire, begeleide* ingang.

---

## 4. Edge cases & guardrails
| Risico | Mitigatie |
|---|---|
| **AVG / per ongeluk publiceren** | De publiceer-/zichtbaarheidspoort blijft een expliciete bevestiging; profielbouw materialiseert als *concept* tot het lid publiceert. Eén schrijf-pad, ongewijzigd. |
| **Te veel proactiviteit** | First-run is **één keer** (flag), dismissbaar; daarna nooit autonoom. Sluit aan op de bestaande attentie-discipline. |
| **Dubbele engine / drift** | We bouwen GEEN tweede profiel-engine; we ontsluiten de bestaande `ai_profile`-materialisatie als canvas-surface. |
| **Herlaad / state** | Profielvorm rendert uit DB-staat (idempotent), zoals nu. Canvas-conversatie-state via `concierge_turn`. |
| **a11y** | Materialisatie kondigt zich aan via de bestaande `aria-live`; reduced-motion-tak behouden. |

---

## 5. Fasering + succescriterium

### Fase 1 — De perceptie omkeren (v0.16.0)
1. First-run walkthrough (één-malig, proactief aanbod + 2-3 voorbeeld-chips).
2. Agent-response-tuning (brede toon-intents → surface zonder filter-eis).
3. Progressive disclosure op de profielvorm (geen lege skeleton + beheer-secties vooraf).
4. `profile_builder`-surface: profielbouw start ín de canvas (materialiseert in-stroom); de dedicated
   pagina blijft als bewerk-/deep-link-bestemming.
5. Tests (first-run één-malig, surface-bouw, consent-poort intact, agent-tuning-regressie) + CHANGELOG.

### Fase 2 — Verrijking (na akkoord)
- Publieke **demo/showcase-walkthrough** voor de bredere launch (buiten besloten preview).
- Draft-tools voor losse profielvelden vanuit de conversatie ("voeg dit project toe" → voorgevuld →
  bevestigen), aansluitend op de Agent-Shell Fase 2 (schrijf-surfaces).

### Succescriterium (PASS/FAIL — eigenaar-oordeel)
Een nieuw lid logt voor het eerst in, krijgt **één** rustig aanbod ("zal ik je profiel opbouwen?"),
typt twee zinnen, en ziet zijn profiel **in de canvas** materialiseren zonder ooit een leeg formulier of
beheer-blok te zien — en oordeelt: dit voelt als 2 minuten praten, niet als werk. Niemand zegt nog
"dat is veel werk".

---

## 6. Open vraag voor de eigenaar (echte keuze — aanbeveling)

**Reikwijdte van Fase 1: hoe ver brengen we profielbouw de canvas in?**

- **(A) (Aanbevolen)** Profielbouw start ín de canvas-conversatie (materialiseert in-stroom via een
  `profile_builder`-surface); de dedicated pagina blijft als bewerk-bestemming. Meest trouw aan "de
  agent is de shell"; lost de pagina-breuk én de perceptie op.
- **(B) Lichter:** behoud de dedicated bouwpagina maar herontwerp 'm met progressive disclosure +
  first-run-guide + agent-tuning; canvas linkt ernaartoe. Sneller te valideren of progressive disclosure
  alléén de perceptie al keert, maar houdt de pagina-breuk.

*Aanbeveling A: de pagina-breuk ("nu begint het werk") is zelf een deel van het probleem; A neemt die
weg. B is een geldige tussenstap als je eerst goedkoper wilt toetsen of disclosure alleen al volstaat.*

---

*Ik begin met Fase 1 (variant A, tenzij je B kiest) zodra dit is goedgekeurd — tenzij je vetoert of de
fork bijstelt.*
