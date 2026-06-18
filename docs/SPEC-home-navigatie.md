---
title: Bouwcontract — Kosmische voordeur (home) + innovatieve navigatie + speelveld-samenhang
status: BUILD-CONTRACT
project: dewereldvan.ai
scope: home '/' herbouw (kosmisch) · herbruikbare nav-partial · speelveld-nav-integratie
look: kosmische diepte (docs/STYLEGUIDE.md) — één look, alles gescoped onder .cosmic
authority: dit document is autoritair; bij conflict wint dit contract boven de losse concepten
date: 2026-06-18
---

# Bouwcontract — Kosmische voordeur + innovatieve navigatie

## 0. Gekozen richting (synthese)

**Ruggengraat = "editorial-verfijnde constellatie-voordeur"** (concept _editorial_ + _constellatie_):
de home is één rustig, levend sterrenveld met een groot Fraunces-statement dat erboven zweeft,
en het hele platform deelt één verfijnde kosmische nav. De wow komt uit **cohesie + precies twee
verfijnde momenten**, niet uit effect-stapeling.

Ingeënt uit de andere concepten (bewust beperkt):
- **Eén levend signaal** uit _levende-hub_: een echt makers-aantal in de eyebrow (`{n} makers`) — geen
  fake, geen count-up-animatie. Géén volledige dashboard-rij (ideeën/roadmap-puls) op de home: dat is
  "over the top" en breekt bij een jonge instance. We tonen het speelveld als **4 poortkaarten**, niet
  als live datavelden.
- **Constellatie-preview** uit _constellatie_: de "Makers"-poortkaart toont 3–5 echte `member-star`-mini's
  als bewijs dat er mensen zijn — maar alléén bij ≥3 publieke leden (anders pure tekstkaart, geen lege gaten).
- **Active-state wayfinding** uit alle drie: de actieve nav-sectie licht op als een ster (gouden glow-dot +
  statische underline). Dit is de "ruimtelijke" twist — maar puur CSS op `aria-current`, geen JS-menu, geen
  hover-glij-gimmick (verworpen: progressive-enhancement-only beweging die niets toevoegt en op zwakke
  devices ruis geeft).

**Verworpen ideeën (1 regel elk):** sticky `backdrop-filter`-nav → GPU-duur op zwakke devices, kies een
semi-opaque fill; live ideeën/roadmap-puls op home → breekt bij lege instance + te druk voor "do not over do it";
hamburger-menu mobiel → JS-state om te onderhouden, kies CSS-only flex-wrap.

**Resultaat:** lost de glaring regressie op (kaal licht formuliertje → kosmische voordeur) én maakt het hele
platform navigeerbaar coherent, met bijna uitsluitend hergebruik van bestaande motieven. **Verdict: PASS.**

---

## A. HOME-SPEC (`/` → `app/templates/index.html`, volledig herschreven)

### A.1 Documentvorm
- Standalone `<body class="cosmic">` document. **`{% extends "base.html" %}` verdwijnt volledig.**
- Kopieer het `<head>`-patroon **1:1 uit `members/index.html`** (regels 8–25): `_seo_head.html` met
  `noindex = false`, Tailwind CDN, htmx, fonts (Fraunces/Spline Sans/JetBrains Mono), `cosmic.css`,
  de `<noscript>`-reveal-fallback. SEO-vars voor de home:
  - `seo_title = "dewereldvan.ai — de wereld van de scherpste AI-makers"`
  - `seo_desc  = "Een besloten plek voor wie in NL & BE serieus met AI bouwt. Maak je profiel, ontdek wat anderen maken, deel waar je naar zoekt."`
  - `og_type = "website"`, `og_image = none`, `jsonld = none`.
- Body-volgorde: `{% include "profiles/_cosmic_bg.html" %}` → `<div class="wrap">` (NIET `--narrow`; de home mag
  breed ademen) → `{% include "_cosmic_nav.html" %}` met `{% set nav_active = "home" %}` ervoor → `<main>` →
  footer (`.c-head` met `© 2026 dewereldvan.ai` + geen "terug"-link want dit ís de wereld) → onderaan
  `{% include "ai/_cosmic_canvas.html" %}` (canvas + reveal-gate). Géén `_feedback_affordance.html` op de
  anonieme home; toon die alleen `{% if request.session.get("member_id") %}` (spiegelt members/index.html r.68).

### A.2 Secties (één skelet; alleen CTA-rij + één eyebrow-woord + 4e kaart verschillen per state)

```
[ _cosmic_nav.html  (nav_active="home") ]                 ← partial uit B
────────────────────────────────────────────────────────
HERO (boven het levende #stars-veld)
  eyebrow   (data-reveal --d:160ms)  → zie microcopy
  headline  (.headline, data-reveal --d:260ms)
  lede      (.lede, max-width:54ch, data-reveal --d:380ms)
  CTA-rij   (data-reveal --d:480ms)  → .btn + .btn--ghost, verschilt per state
────────────────────────────────────────────────────────
HET SPEELVELD  (.section-title, data-reveal --d:560ms)
  .home-gates  (= .grid hergebruik) met a.card "poorten":
    1. De makers   → /leden      (toont member-star-preview indien ≥3 publieke leden)
    2. Ideeën      → /ideeen  (anon) of /ideeen (ingelogd)   ← zie A.4
    3. Roadmap     → /roadmap (anon) of /roadmap (ingelogd)  ← zie A.4
    4. Jouw profiel → /profiel/ai/bouwen   (ALLEEN ingelogd)
────────────────────────────────────────────────────────
footer .c-head  © 2026 dewereldvan.ai
```

De getrapte `[data-reveal]`-entree (bestaand, via `_cosmic_canvas.html` → `.ready`) is **het primaire
animatie-moment**. Geen extra hero-animatie schrijven.

### A.3 De twee verfijnde momenten (en niet meer)
1. **Typografie boven het levende sterrenveld.** Het bestaande `#stars`-canvas is de hero-achtergrond, niet
   slechts sfeer. Grote Fraunces-headline + getrapte reveal = "dit IS de wereld" zonder één nieuwe regel motion.
2. **Eén echt signaal in de eyebrow:** `{{ member_count }} makers` als gouden mono-accent. Geen count-up.
   Verbergen bij `member_count == 0` (toon dan alleen `DE WERELD VAN`-eyebrow zonder getal).

Optioneel-derde (alléén indien goedkoop): **constellatie-preview** in de "De makers"-poortkaart — 3–5
`member-star__avatar`/`__initials`-mini's uit `preview_stars`. Bij `< 3` publieke leden: pure tekstkaart,
geen halflege rij. Dit is een _augment_ van de kaart, geen eigen sectie.

### A.4 States — microcopy (gewone, directe NL; nooit zweverig)

**Anoniem** (`request.session.get("member_id")` is falsy):
- eyebrow: `DE WERELD VAN` + (indien `member_count > 0`) ` · {{ member_count }} MAKERS`
- headline: `De wereld van de scherpste AI-makers.`
- lede: `Een besloten plek voor wie in NL & BE serieus met AI bouwt. Maak je profiel, ontdek wat anderen maken, deel waar je naar zoekt.`
- CTA: `[ Word lid ]` (`.btn` → `/register`) · `[ Bekijk de makers ]` (`.btn--ghost` → `/leden`)
- Poortkaarten: 3 kaarten → `De makers` (/leden), `Ideeën` (/ideeen), `Roadmap` (/roadmap).
  - `/leden` is publiek → echte deur. `/ideeen` en `/roadmap` vereisen login (`require_member`); de anon-kaart
    blijft naar `/ideeen` resp. `/roadmap` wijzen (de route redirect zelf netjes naar `/login`) **met een mono-
    sublabel `voor leden`** op de kaart — geen kapotte/verborgen deur, eerlijk gelabeld.
  - Geen 4e kaart.

**Ingelogd** (`member_id` truthy):
- eyebrow: `WELKOM TERUG` + (indien `member_count > 0`) ` · {{ member_count }} MAKERS`
- headline: `Welkom in de wereld.`
- lede: `Ga verder met je profiel, of ontdek wat de anderen maken.`
- CTA: `[ Naar mijn profiel ]` (`.btn` → `/profiel/ai/bouwen`) · `[ Ontdek de makers ]` (`.btn--ghost` → `/leden`)
- Poortkaarten: 4 kaarten → `De makers` (/leden), `Ideeën` (/ideeen), `Roadmap` (/roadmap),
  `Jouw profiel` (/profiel/ai/bouwen). Alle echte deuren, geen `voor leden`-sublabels.

Signaalregel-regel: toon het makers-getal **alleen** bij `member_count > 0`. Nooit "0 makers".

### A.5 Context die `/` MOET meegeven (route-wijziging in `app/main.py`, sectie E)
De route geeft, naast `request`, mee:
- `member_count: int` — aantal publieke, goedgekeurde makers. **Afleiden uit bestaande service**, geen nieuwe
  query-stijl introduceren: `len(members_service.list_public_profiles(db))` is acceptabel (zelfde poort/eager-load
  als /leden). Mag als kleine helper `count_public_profiles(db)` in `members_service` als `len(list(...))` te grof
  voelt — dan getest meeleveren.
- `preview_stars: list[Profile]` — `members_service.list_public_profiles(db)[:5]` voor de Makers-kaart-preview.
  Template rendert preview alleen bij `preview_stars | length >= 3`.
- `photo_for` + `emphasis_class` — **alleen meegeven indien** de preview de `member-star`-partial hergebruikt
  (die verwacht `photo_for`/`emphasis_class` callables): `photo_service.photo_or_initials` resp.
  `emphasis_service.emphasis_class`. Als de preview een simpeler eigen avatar-render doet (initialen/foto inline),
  hoeven deze callables niet mee — kies de simpele variant om de koppeling klein te houden.
- `nav_active` wordt in de **template** gezet (`{% set nav_active = "home" %}`), niet via de route.

De `/`-route krijgt hiervoor een `db: Session = Depends(get_db)`-dependency, **exact spiegelend** aan
`members.router` (`from app.db import get_db`). Geen eigen sessie-patroon.

---

## B. NAV-SPEC (`app/templates/_cosmic_nav.html` — NIEUW)

Vervangt de ad-hoc `.c-head`-headers (brand + 1–2 losse `.link`s) op alle speelveld-pagina's uit sectie D
door één consistente, verfijnde balk.

### B.1 Context-vars (de partial leest zelf uit `request`; minimaal door routes te zetten)
| Var | Bron | Default | Effect |
|-----|------|---------|--------|
| `request.session.get("member_id")` | sessie (overal beschikbaar) | — | bepaalt login-state-slot |
| `nav_active` | per pagina `{% set nav_active = "..." %}` vóór de include | `""` | actief item: `"home"\|"leden"\|"ideeen"\|"roadmap"\|"profiel"` |
| `is_admin` | optioneel; routes die de `member` al laden mogen `is_admin = (member.role == MemberRole.admin)` meegeven | `false` | toont discrete `Beheer`-link |
| `member_slug` | optioneel | `none` | reserve voor "Mijn profiel"→profiel-deeplink; **fallback altijd `/profiel/ai/bouwen`** |

Belangrijk: er is **géén `is_admin` session-key** in dit project (admin = `member.role == MemberRole.admin`,
zie `app/deps.py:52`). De partial mag daarom **niet** op `request.session.get("is_admin")` vertrouwen. De
`Beheer`-link is puur gegate op de optionele `is_admin`-context-var; routes zonder geladen member (zoals `/`)
geven die niet mee → geen Beheer-link op de home. Dat is correct en veilig (geen lek).

### B.2 Markup-structuur (exact)
```html
{# Herbruikbare kosmische hoofdnav. Vervangt de ad-hoc .c-head-headers.
   Leest request.session voor login-state; verwacht optioneel nav_active (str),
   is_admin (bool), member_slug (str). Werkt zonder JS; reduced-motion-safe. #}
<nav class="cnav" aria-label="Hoofdnavigatie" data-reveal style="--d:60ms">
  <a class="brand" href="/"><span class="dot"></span> dewereldvan.ai</a>

  <div class="cnav__links">
    <a class="cnav__link {% if nav_active == 'leden' %}cnav__link--active{% endif %}"
       href="/leden" {% if nav_active == 'leden' %}aria-current="page"{% endif %}>Makers</a>
    <a class="cnav__link {% if nav_active == 'ideeen' %}cnav__link--active{% endif %}"
       href="/ideeen" {% if nav_active == 'ideeen' %}aria-current="page"{% endif %}>Ideeën</a>
    <a class="cnav__link {% if nav_active == 'roadmap' %}cnav__link--active{% endif %}"
       href="/roadmap" {% if nav_active == 'roadmap' %}aria-current="page"{% endif %}>Roadmap</a>
  </div>

  <div class="cnav__end">
    {% if is_admin %}
    <a class="cnav__link cnav__link--admin" href="/admin/queue">Beheer</a>
    {% endif %}
    {% if request.session.get("member_id") %}
    <a class="cnav__link {% if nav_active == 'profiel' %}cnav__link--active{% endif %}"
       href="/profiel/ai/bouwen" {% if nav_active == 'profiel' %}aria-current="page"{% endif %}>Mijn profiel</a>
    {% else %}
    <a class="cnav__link" href="/login">Inloggen</a>
    <a class="btn btn--ghost btn--sm" href="/register">Word lid</a>
    {% endif %}
  </div>
</nav>
```
- Brand-`.dot` + `.brand` worden **hergebruikt** (bestaande classes, regels 145–159 cosmic.css) → twinkelende
  gouden ankerster, consistent met de hele site. Brand → altijd `/` (de terugweg naar de wereld).
- `Beheer`-href = `/admin/queue` (verifieer het exacte admin-queue-pad in `app/routers/admin.py` bij implementatie;
  als het pad afwijkt, gebruik het werkelijke pad — niet raden).
- De `btn--ghost.btn--sm` voor "Word lid" hergebruikt bestaande btn-classes (geen nieuwe class).

### B.3 Interactie / a11y / reduced-motion (hard vereist)
- **Semantiek:** echte `<a>`'s in `<nav aria-label="Hoofdnavigatie">`. Actief item krijgt `aria-current="page"`.
- **Toetsenbord:** native tab-order; focus via bestaande cyan `:focus-visible`-ring (volg het patroon van
  `.member-star:focus-visible`, cosmic.css:550 — voeg een `.cnav__link:focus-visible`-regel toe die diezelfde
  ring-taal hergebruikt). Geen JS-only interacties, geen tab-traps.
- **Active-state visueel:** `.cnav__link--active` = statische gouden glow-dot (`::before`, recept van `.brand .dot`
  box-shadow) + dunne `--gold` underline. **Statisch, geen puls** → valt al onder de bestaande
  `.cosmic *{animation:none}`-reduced-motion-regel; blijft volledig zichtbaar zonder motion.
- **Mobiel (≤640px):** CSS-only. De drie midden-links + end-slot mogen `flex-wrap` naar een tweede regel
  (kleinere mono-tekst), brand blijft links. **Geen hamburger, geen JS-toggle.** Alles altijd zichtbaar.
- **De brand-dot-twinkel** dooft al onder reduced-motion (bestaande regel). Geen nieuwe animatie toevoegen die
  niet onder die regel valt.

### B.4 Waarom dit "innovatief maar niet over the top" is
Functioneel een gewone, leesbare topnav (links die werken zonder JS). De "innovatie" is puur **cohesie**:
sterren-taal (brand-dot) + active-glow als wayfinding ("je ziet ruimtelijk waar je bent"). Eén bestaand motief
hergebruikt, geen nieuw interactiemodel om te leren. De grootste UX-winst is dat 5 inconsistente `.c-head`-
lijstjes één verfijnde balk worden.

---

## C. CSS-SPEC (`app/static/cosmic.css` — uitsluitend onder `.cosmic`, op bestaande tokens)

**Harde limiet: ≤ 6 nieuwe class-selectors. Geen nieuwe fonts, geen nieuwe hex-waarden buiten de tokens
(`--gold`, `--cyan`, `--muted`, `--text`, `--line`, `--card`).**

### Nav (≤4)
| Selector | Gedrag |
|----------|--------|
| `.cosmic .cnav` | erft `.c-head`-typografie (mono 12.5px, letter-spacing); `display:flex; justify-content:space-between; align-items:center; gap:18px; padding:26px 0; flex-wrap:wrap`. **Niet** sticky met `backdrop-filter` (verworpen: GPU-duur). Indien sticky gewenst: `position:sticky; top:0; background:rgba(4,4,14,.72); border-bottom:1px solid var(--line); z-index:5` — semi-opaque fill, géén blur. Default: niet-sticky (eenvoudigst). |
| `.cosmic .cnav__links`, `.cosmic .cnav__end` | `display:flex; gap:18px; align-items:center; color:var(--muted)`. `.cnav__end` mag `margin-left:auto` als de wrap-volgorde dat vereist. |
| `.cosmic .cnav__link` | `color:var(--muted); text-decoration:none; position:relative; transition:color .25s`. `:hover` → `color:var(--gold)`. `:focus-visible` → cyan ring (hergebruik ring-taal van `.member-star:focus-visible`). |
| `.cosmic .cnav__link--active` | `color:var(--text)`; `::before` = gouden glow-dot (`content:""; width:5px;height:5px;border-radius:50%;background:var(--gold);box-shadow:0 0 10px 2px var(--gold)`), of een statische `--gold` underline via `::after`. Statisch (geen `animation`). |

`.cnav__link--admin` en de mobiele `@media(max-width:640px)`-aanpassing tellen **niet** als nieuwe component-classes
(`--admin` is een modifier; de media-query stuurt bestaande `.cnav*`). Houd ze minimaal.

### Home (≤2)
| Selector | Gedrag |
|----------|--------|
| `.cosmic .home-gates` | **Bij voorkeur hergebruik puur `.grid`** (auto-fill minmax 240px). Voeg deze class alléén toe als layout-spacing/kolom-cap het echt vereist (bv. `margin-top` of max 4 kolommen). |
| `.cosmic .home-gate__note` | mono `--muted` sublabel ("voor leden" / preview-caption). Alléén indien de bestaande `.chip`/`.eyebrow--plain` niet volstaat. |

**Doel: liefst 0 home-classes** (alles via `.grid` + `a.card` + `.section-title` + `.eyebrow` + `.btn`).
De member-star-preview hergebruikt `member-star__avatar`/`__initials` — **geen nieuwe preview-classes**.

---

## D. INTEGRATIE-SCOPE (waar de nav-partial komt)

Vervang het ad-hoc `<header class="c-head">…</header>`-blok door `{% include "_cosmic_nav.html" %}` (met de
juiste `nav_active` ervoor gezet) op **precies deze 4 speelveld-pagina's**:

| Template | `nav_active` | Bijzonderheid |
|----------|--------------|---------------|
| `app/templates/members/index.html` (`/leden`) | `"leden"` | header-blok r.30–39 → include; footer (r.62–65) blijft |
| `app/templates/ideas/index.html` (`/ideeen`) | `"ideeen"` | header r.23 → include; footer blijft |
| `app/templates/roadmap/index.html` (`/roadmap`) | `"roadmap"` | header r.23 → include; footer blijft |
| `app/templates/ai/live.html` (`/profiel/ai/bouwen`) | `"profiel"` | **ALLEEN** header r.38–44 → include. SSE/materialisatie/slots NIET aanraken (hard mandaat). Let op: deze header bevat nu óók "Handmatig bewerken" → na de nav-include is die link weg uit de header; dat is acceptabel (de nav dekt navigatie). |

**Buiten scope (behouden eigen header/focus):**
- `app/templates/profiles/view.html` (`/leden/{slug}`) en `app/templates/projects/view.html` (`/projecten/{slug}`):
  publieke detailpagina's, mogen hun focus/eigen header houden. Niet aanraken in deze sessie (vermijdt SEO-risico
  + houdt teams disjunct). Opvolg-learning indien later uniformering gewenst.
- `app/templates/profiles/edit.html` (licht thema, bewuste uitzondering): GEEN cosmic-nav.
- `app/templates/index.html`: krijgt de nav óók, maar dat bestand is **core-team-eigendom** (zie E), niet
  integratie-team.

**Voor elk integratie-template geldt: ALLEEN het header-blok vervangen. Geen andere regel aanraken.**
Na de wijziging: `grep -rn "class=\"c-head\"" app/templates/` mag alléén nog footers + out-of-scope-pagina's tonen.

---

## E. FILE-OWNERSHIP-MATRIX (disjunct — geen bestand door twee teams)

### CORE-team (home + nav + css + route + tests)
- `app/templates/index.html` — herschrijven naar standalone cosmic (sectie A)
- `app/templates/_cosmic_nav.html` — NIEUW (sectie B)
- `app/static/cosmic.css` — ≤6 nieuwe classes (sectie C)
- `app/main.py` — `index()`-route: `db`-dependency + `member_count`/`preview_stars`(+evt. callables) context (sectie A.5)
- `tests/test_home.py` — NIEUW (sectie F)
- (indien gekozen) kleine `count_public_profiles`-helper in `app/services/members_service.py` + test ervoor.
  **Let op:** als integratie-team óók members raakt zou dat botsen — maar integratie-team raakt alléén
  `members/index.html` (template), niet `members_service.py`. Disjunct blijft gewaarborgd.

### INTEGRATIE-team (alleen header→nav-include op de 4 speelveld-templates uit D)
- `app/templates/members/index.html`
- `app/templates/ideas/index.html`
- `app/templates/roadmap/index.html`
- `app/templates/ai/live.html`
- (test-touch) mag een assertie toevoegen in een **eigen** testbestand `tests/test_nav_integration.py` (NIEUW),
  niet in `tests/test_home.py`.

**Geen overlap:** core bezit `index.html` + nav-partial + css + route + `test_home.py`; integratie bezit de 4
andere templates + `test_nav_integration.py`. `cosmic.css`, `main.py`, `members_service.py` zijn uitsluitend core.
De nav-partial wordt door integratie **alleen geïncludeerd**, nooit bewerkt.

### NIET AANRAKEN (beide teams)
`VERSION`, `CHANGELOG.md`, `requirements.txt` (orchestrator bumpt/committeert). `app/services/*`-gedrag,
`app/routers/ai_profile.py`-handlers, `ai/slots/*`, `ai/_cosmic_canvas.html`/`profiles/_cosmic_bg.html`
(alleen includen, niet wijzigen), `_seo_head.html`.

---

## F. TEST-SPEC

### CORE — `tests/test_home.py` (NIEUW)
Gebruik de bestaande test-client/fixtures (SQLite in-memory; zie `pytest` in CLAUDE.md). Assert:
1. **Anon render 200:** `GET /` → 200, body bevat `class="cosmic"`, bevat de nav (`cnav` of `Hoofdnavigatie`),
   bevat de canvas-include-marker (`#stars` / `_cosmic_canvas` artefact), bevat `Word lid` + `/leden`-CTA, en
   bevat **NIET** de lichte-thema-string `text-slate-900` of `De wereld van ons` (regressie-guard).
2. **Ingelogd render 200:** met gemockte sessie (`member_id` gezet, zoals bestaande auth-tests doen) → 200,
   bevat `Naar mijn profiel` (→`/profiel/ai/bouwen`) en `Ontdek de makers`.
3. **Signaal-gating:** met 0 publieke leden verschijnt géén `makers`-getalregel; met ≥1 publiek lid verschijnt
   `{n} MAKERS` in de eyebrow.
4. **Preview-gating:** met `< 3` publieke leden geen member-star-preview in de Makers-kaart; met ≥3 wel.
5. **SEO-intact:** `GET /` is indexeerbaar (geen `noindex`-meta; canonical/og aanwezig via `_seo_head`).
6. (indien helper gebouwd) unit-test op `count_public_profiles` met een approved+public vs besloten/geschorst lid.

### INTEGRATIE — `tests/test_nav_integration.py` (NIEUW)
1. **Nav aanwezig:** `GET /leden`, `/ideeen` (ingelogd), `/roadmap` (ingelogd), `/profiel/ai/bouwen` (ingelogd)
   → elke respons bevat de nav-marker (`aria-label="Hoofdnavigatie"` / `cnav`).
2. **Active-state:** op `/leden` heeft de Makers-link `aria-current="page"`; op `/roadmap` de Roadmap-link.
3. **SEO van `/leden` blijft groen:** de bestaande SEO-test op `/leden` mag niet breken (nav vervangt `_seo_head`
   niet). Draai de bestaande members-SEO-test mee.
4. **ai/live.html ongemoeid:** `/profiel/ai/bouwen` rendert nog steeds de SSE-/slot-structuur (assert een bestaand
   slot-/canvas-artefact aanwezig) — alleen de header is vervangen.

### GEZAMENLIJK (kwaliteitspoort)
- `pytest` volledige suite **groen**.
- App **boot**: import van `app.main` + `create_app()` zonder fouten; `GET /healthz` → 200.
- `grep -rn 'class="c-head"' app/templates/` toont na afloop alléén footers + out-of-scope (profiles/projects view,
  edit) — geen speelveld-pagina-**header** meer met los `.c-head`.

---

## G. Risico's + mitigaties (autoritair)
1. **Lege/jonge instance** (0–3 makers): signaalregel verbergen bij 0; member-star-preview alléén bij ≥3; copy
   ("Een besloten plek voor wie serieus met AI bouwt") klopt ook zonder getallen.
2. **`/`-route doet nu DB-query** (was query-loos): één `list_public_profiles`-call, eager-loaded, `[:5]`-slice
   licht. Bestaande index-test aanpassen + nieuwe home-tests.
3. **Active-state pad-match:** drijft op `nav_active` (server-side, expliciet per pagina) — robuuster dan
   pad-`startswith` (geen `/leden` vs `/leden/{slug}`-verwarring). Default `""` = niets actief, veilig.
4. **Admin-link zonder session-key:** uitsluitend via optionele `is_admin`-context; geen `request.session`-aanname.
   Routes zonder geladen member tonen géén Beheer-link (correct).
5. **Twee canvassen / duplicatie van #stars-script over pagina's:** geaccepteerd (consistent met bestaand patroon,
   full-page loads → geen runtime-conflict). Niet refactoren naar gedeelde JS in deze sessie (scope-creep).
   Opvolg-learning.
6. **Sticky-nav GPU-kost:** default niet-sticky; indien sticky → semi-opaque fill zonder `backdrop-filter`.

---

## H. Definition of Done
- [ ] `/` rendert kosmisch (standalone `.cosmic`), anon + ingelogd, met nav + canvas; geen lichte-thema-restanten.
- [ ] `_cosmic_nav.html` bestaat, a11y-correct (`aria-current`, focus-ring), reduced-motion-safe, mobiel CSS-only.
- [ ] De 4 speelveld-pagina's gebruiken de nav-include i.p.v. los `.c-head`-header; `ai/live.html` enkel header.
- [ ] ≤6 nieuwe cosmic.css-classes, op tokens, geen tweede look/font/hex.
- [ ] `tests/test_home.py` + `tests/test_nav_integration.py` groen; volledige `pytest`-suite groen; app boot; `/healthz` 200.
- [ ] Geen wijziging aan VERSION/CHANGELOG/requirements/AI-engine-gedrag.
