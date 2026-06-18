# dewereldvan.ai — Styleguide & ervaringsrichtlijnen

> **"Kosmische diepte."** Eén identiteit, overal. Dit document is verplichte lectuur vóór elk
> scherm, elke flow en elke e-mail. Zie ook het **Ervaringsmandaat** in `CLAUDE.md`.

## 0. Het principe (de lat)
De leden zijn de scherpste AI-mensen van NL/BE. **Alles op dewereldvan.ai moet hen verbazen —
altijd, iedereen, overal.** Een kale interactie of generieke "AI-startup"-look is een regressie.
De toetssteen bij élk scherm: *"Verrast dit iemand die dagelijks met AI bouwt?"* Zo nee → niet af.

Twee assen, allebei verplicht:
1. **Verfijnd & verrassend** — visueel en in motion (deze styleguide).
2. **Superslim** — de interface helpt actief (feedback overal, suggesties, AI-assist). Zie §6.

---

## 1. Visuele identiteit — "kosmische diepte"

### Kleur (canonieke tokens — in `app/static/cosmic.css`)
| Token | Waarde | Gebruik |
|-------|--------|---------|
| `--bg-0` | `#04040e` | Basis (bijna-zwart indigo) |
| `--bg-1` | `#0a0a24` | Tweede laag |
| `--indigo` | `#15123a` | Velden, kaarten |
| `--violet` | `#6d5dfc` | Nebula-gloed |
| `--cyan` | `#3fd2ff` | Nebula-gloed, focus |
| `--magenta`| `#b15cff` | Nebula-gloed |
| `--gold` | `#f6cd86` | **S, scherpe accentkleur** (CTA, key-ster) — spaarzaam |
| `--text` | `#eef0ff` | Tekst |
| `--muted` | `#9097c4` | Secundair / mono-labels |

Donker is de default. Eén dominante kleur (indigo) + één scherp accent (goud). Geen timide,
gelijk-verdeelde paletten. **Nooit** paarse-gradient-op-wit (de generieke AI-look).

### Typografie
- **Display**: **Fraunces** (serif, optisch, karaktervol) — koppen, hero, namen.
- **Mono/labels**: **JetBrains Mono** — eyebrows, status, metadata, kleine labels (`letter-spacing` ruim).
- **Body**: **Spline Sans** (300/400) — lopende tekst.
- Via Google Fonts in `base.html`. Géén Inter/Roboto/Arial/system-ui voor sier.

### Achtergrond & sfeer (altijd aanwezig, nooit een platte kleur)
- Driftende **nebula-mesh** (violet/magenta/cyan blobs, `blur`, `mix-blend-mode: screen`, trage drift).
- **Cyaan-gloed** als zachte puls.
- **Filmkorrel** (`grain`, lage opacity, overlay) + **vignet** voor diepte.
- **Levende constellatie** (canvas): driftende sterren die verbindingslijnen vormen bij nabijheid +
  parallax op muis — het handtekening-element ("netwerk van makers"). Hergebruik het teaser-canvas
  (`teaser/index.html`) en de `_cosmic_*`-partials.

### Motion
- **Gechoreografeerde page-load**: gestaggerde reveals (eyebrow → kop → tekst → actie) met blur→scherp.
- Hoog-impact momenten boven micro-fireworks. Hover/focus die verrast (gloed, lift).
- **Alles respecteert `prefers-reduced-motion`** → animaties uit, content direct zichtbaar. Geen uitzondering.

### Compositie
Royale negatieve ruimte óf bewuste dichtheid — nooit toevallig. Asymmetrie, overlap, grid-breaking
mag. Niet centreren "omdat het moet".

---

## 2. Componenten & patronen
- **Knoppen**: pill-vorm; primair = goud-gradient op donker, met lift + gloed op hover; mono-label.
- **Inputs**: subtiele glas-fill, ronde rand; focus = cyaan rand + zachte gloed-ring.
- **Kaarten** (profiel-links, projecten, ideeën): indigo glas, rand `--line`, beeld + titel + mono-meta.
- **Eyebrow**: mono, uppercase, ruime `letter-spacing`, goud, met een kort gradient-lijntje ervoor.
- **Cosmic background** als herbruikbare partial (`_cosmic_bg`) op elke kern-pagina.
- htmx voor interactie; SSE voor streaming (AI-antwoorden, live updates). Geen JS-buildpipeline.

---

## 3. Microcopy & toon
- **Nederlands. Eenvoudig, direct, to the point** — warm-menselijk, nooit corporate of klef,
  en **niet zweverig of poëtisch**. In-app schrijven we gewone, heldere taal. De verbazing zit in
  de **ervaring en de intelligentie**, niet in bloemrijke woorden.
  - ❌ "Je ster is verschenen", "de rest verbindt vanzelf", "het universum wacht op je"
  - ✅ "Welkom", "Laten we aan jouw profiel werken", "Je profiel staat zo klaar"
- Spreek de maker aan als peer ("Vertel wie je bent", niet "Vul uw gegevens in").
- Korte, concrete zinnen: zeg wat er gebeurt en wat de volgende stap is.
- Een **woordgrap die past** mag (dewereldvan.ai = "de wereld van AI") — maar nooit ten koste van
  helderheid.
- Lege staten, succes-staten en fouten krijgen óók aandacht — helder en behulpzaam.

---

## 4. Interactie-intelligentie (de "superslim"-as)
Verplicht meegenomen in elk relevant scherm:
- **Feedback overal**: een altijd-bereikbare manier om feedback/suggestie achter te laten op de site
  (zie de ideeënbus/feedback-feature). Niet weggestopt in een contactformulier.
- **Suggesties**: de UI biedt proactief next steps / verbeteringen aan (bv. "je profiel mist nog X",
  AI-suggesties voor projecten/tags).
- **AI-assist**: waar het helpt, doet Claude het zware werk (profielbouw, samenvatten, voorstellen).
- **Centrale pagina's** (roadmap, ideeënbus) zijn levend en transparant, in dezelfde identiteit.

---

## 5. Toegankelijkheid & vindbaarheid (verrassing ≠ ontoegankelijk of onvindbaar)
- `prefers-reduced-motion` altijd gehonoreerd. Voldoende contrast (tekst op donker).
- Volledige toetsenbordbediening, zichtbare focus-states (de cyaan gloed telt mee), aria waar nodig.
- Responsive: de ervaring is even sterk op mobiel (de meeste leden delen via WhatsApp → mobiel first-touch).
- **Linkwaarde/SEO is een expliciet doel** voor publieke content (leden + projecten): schone, stabiele
  slugs + canonical URLs, OG/Twitter-tags, JSON-LD (`Person`/`CreativeWork`), `sitemap.xml` + `robots.txt`.
  Alleen publieke content indexeerbaar; besloten = `noindex` + login-gated. Zie `docs/PRD-ledenpagina.md`.

---

## 6. Per-scherm checklist (af = alle vinkjes)
- [ ] Kosmische achtergrond aanwezig (nebula/gloed/grain/vignet, evt. constellatie)
- [ ] Fraunces + JetBrains Mono + Spline Sans correct ingezet
- [ ] Gechoreografeerde entrance + doordachte hover/focus
- [ ] `prefers-reduced-motion`, contrast, toetsenbord, responsive OK
- [ ] Microcopy is eenvoudig, direct en to the point (niet zweverig); spreekt de maker als peer aan
- [ ] Een slimme hulp aanwezig (feedback/suggestie/AI) waar relevant
- [ ] Lege/fout/succes-staten ook af
- [ ] Geen tweede look geïntroduceerd; `cosmic.css`-tokens hergebruikt
- [ ] Toetssteen gehaald: *"Dit verrast iemand die dagelijks met AI bouwt."*

---

## 7. Anti-patterns (NOOIT)
- Een kaal formulier op een witte/grijze pagina. Generieke AI-startup-look. Paarse gradient op wit.
- Inter/Roboto/Arial als sierfont. Platte solide achtergrond zonder sfeer.
- "We fixen de styling later" — styling is geen latere fase, het is de feature.
- Een tweede, afwijkende huisstijl introduceren. Toegankelijkheid opofferen voor effect.
- **Zweverig/poëtisch taalgebruik** ("je ster is verschenen", "het universum wacht"). In-app = eenvoudig en to the point.
- **Auto-redirects als "ervaring"** (een pagina die je na X seconden wegklikt). Een onboarding is een moment waar de maker zélf doorklikt, geen doorverwijspagina.
