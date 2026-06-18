# PRD — Publieke demo/showcase ("door AI gemaakt", fictief profiel)

**Status:** 🟡 TER GOEDKEURING (2026-06-19) — wacht op fork-keuze vóór bouw
**Versie-doel:** 0.20.0 (MINOR — nieuwe publieke feature)
**Datum:** 2026-06-19
**Bouwt voort op:** de live Agent-Shell (v0.19.0).

> **Eigenaar-eis (2026-06-19):** een publieke demo/showcase, bij voorkeur met een **fictief profiel**
> en **fictieve website**, "echt een duidelijke **'door AI gemaakte demo'**".

---

## 0. Eén regel

Een publieke pagina (`/demo`, geen login) die de wow van de Agent-Shell aan een buitenstaander laat
zien: de agent bouwt vóór je ogen een **fictief** makersprofiel op uit een **fictieve** website —
duidelijk gelabeld als een door-AI-gemaakte demo, met een heldere brug naar "word zelf lid".

---

## 1. Doel + waarom

De besloten preview overtuigt leden; de **publieke launch** moet een bezoeker in 20 seconden laten
voelen wat dit is — zonder account, zonder uitleg. De sterkste demonstratie is precies de "te
standaard"-breker: je geeft een link en het profiel materialiseert. Dat tonen we met een fictieve
maker, zodat er geen echte persoonsdata in het spel is en het onmiskenbaar een demo is.

---

## 2. De ene echte keuze: live AI of gescript? (de fork)

Dit bepaalt de hele bouw én de kosten/risico's van een **publieke** pagina:

- **(A) (Aanbevolen) Gescripte replay — geen AI-calls.** De demo speelt een vooraf-vastgelegde sequentie
  af met exact dezelfde kosmische materialisatie-esthetiek (reasoning-gloed → "site scannen ✓" →
  velden materialiseren één voor één) op **vaste, fictieve** data. Nul AI-kosten, nul misbruik-oppervlak,
  deterministisch, werkt altijd, indexeerbaar (SEO). Past bij lage-op-last + kostenbeheersing. Het is
  letterlijk een "door AI gemaakte demo": de inhoud is ooit door de AI gemaakt en wordt nu afgespeeld.
- **(B) Live interactieve sandbox — echte AI.** Anonieme bezoekers typen zelf; de echte agent bouwt een
  wegwerp-profiel. Maximale "echtheid", maar: **AI-kosten per bezoeker + misbruik-vector** (prompt-
  injectie, spam, kosten-bombing) op een open pagina → vereist harde rate-limiting/guardrails. Tegen de
  lage-op-last/kosten-eis.
- **(C) Hybride.** Gescripte auto-play (A) + een optionele "probeer het zelf"-knop met een paar
  streng-gelimiteerde echte interacties. Beste gevoel, maar erft B's kosten/misbruik-zorg (kleiner).

*Aanbeveling A: een publieke, altijd-aan, geïndexeerde pagina hoort geen open AI-kraan te zijn. Een
gescripte replay levert dezelfde visuele wow zonder kosten/misbruik en is onmiskenbaar "een AI-demo".
Wil je later live laten proeven, dan voegen we C toe achter login/rate-limit.*

---

## 3. De fictieve maker (voorstel — pas gerust aan)

Onmiskenbaar fictief, herkenbaar in de doelgroep:

- **Naam:** *Nova Belmonte* (fictief)
- **Fictieve site:** `studio-nova.ai` (bestaat niet — wordt nergens echt gefetcht; de "scan" is gescript)
- **Bouwt:** stem-AI-companions voor podcasters; AI-beleidsadvies voor de cultuursector
- **Tags:** voice-agents, audio, beleid, creative-AI
- **Zoekt:** een mede-bouwer voor realtime audio

Overal een duidelijk label: **"✦ Demo — fictief profiel, door AI opgebouwd"**.

---

## 4. De ervaring (variant A)

1. Bezoeker landt op `/demo` (publiek, geen login). Kosmische canvas, demo-badge bovenaan.
2. Een "speel af"-moment (auto-play of één klik): in het canvas-veld "verschijnt" `studio-nova.ai`.
3. De gescripte stroom: reasoning-gloed → "·· studio-nova.ai scannen ✓" → headline, bio, projecten,
   tags, "wat ik zoekt" materialiseren één voor één (zelfde `field--materializing`-choreografie).
4. Daarna een rustige **call-to-action**: "Zo bouw jij ook je profiel — in een paar minuten.
   [Word lid]" → `/register`.
5. Optioneel (Fase 2): "bekijk de makers" toont een **fictieve** mini-constellatie (duidelijk demo).

Eenvoudige, directe taal; de demo-badge laat geen twijfel dat het fictief is.

---

## 5. Architectuur — hergebruik vs. nieuw (variant A)

### 5.1 Hergebruikt 1:1
- De kosmische materialisatie-esthetiek + CSS (`field--materializing`/`reasoning`/cosmic tokens).
- De canvas-/profielvorm-partials (gevuld met fictieve data i.p.v. DB).
- `_cosmic_bg`/`ai/_cosmic_canvas`/typografie.

### 5.2 Nieuw (afgebakend)
- Publieke route `GET /demo` (geen auth, `index`-able) → een standalone demo-document.
- Een **gescript stroom-mechanisme** (client-side JS-eiland of een vaste SSE die canned events afspeelt
  met dezelfde timing) — géén Anthropic-call, géén echte `web_fetch`.
- Vaste fictieve-data-fixture (de Nova-persona) + de demo-badge + de CTA.
- Geen datamodel-wijziging (de demo raakt de DB niet).

---

## 6. Guardrails
| Risico | Mitigatie |
|---|---|
| **Misverstand "is dit een echt lid?"** | Permanente "✦ Demo — fictief profiel" badge; fictieve naam/site; geen link naar een echt profiel. |
| **AI-kosten/misbruik op een open pagina** | Variant A doet GEEN AI-call. (B/C alleen achter rate-limit/login.) |
| **Echte persoonsdata** | Uitsluitend verzonnen data; raakt de ledendatabase niet. |
| **SEO/spoofing** | `/demo` indexeerbaar met duidelijke demo-framing; de fictieve site wordt nooit echt gefetcht. |

---

## 7. Fasering + succescriterium

### Fase 1 — De gescripte demo (v0.20.0, bij keuze A)
1. `GET /demo` + standalone demo-document + demo-badge.
2. Gescript materialisatie-stroom op de Nova-fixture (zelfde esthetiek).
3. CTA → `/register`. Tests (route 200, badge aanwezig, geen AI-call-pad) + CHANGELOG.

### Fase 2 — Verrijking
- Fictieve mini-constellatie ("bekijk de makers"); evt. variant C ("probeer het zelf", gelimiteerd).

### Succescriterium (PASS/FAIL)
Een bezoeker zonder account opent `/demo`, ziet binnen ~20s een profiel uit "een website" materialiseren,
begrijpt onmiddellijk dat het een AI-demo met een fictief profiel is, en weet wat de volgende stap is
("word lid"). Geen AI-kosten per bezoek.

---

## 8. Open vraag voor de eigenaar

**De fork van §2: A (gescript, aanbevolen), B (live), of C (hybride)?** En akkoord op de fictieve
persona (§3) of een eigen voorkeur?

*Ik begin met variant A + de Nova-persona zodra je dit bevestigt — tenzij je B/C kiest of de persona
bijstelt.*
