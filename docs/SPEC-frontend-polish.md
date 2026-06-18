# SPEC — Frontend Polish (launch-klaar maken)

**Status: BUILD-CONTRACT**
**Doel:** de resterende lichte (Tailwind-emerald / `base.html`) pagina's kosmiseren tot launch-niveau, zodat de wachtlijst uitgenodigd kan worden. Conform mandaat: verfijnd, rustig, cohesief — geen gimmicks; eenvoudige directe NL-microcopy.

**Synthese van 3 audits** (auth-funnel · edit-admin · detail-laag). Funnel-prioriteit: **auth + foutpagina's + e-mails/assets eerst**, daarna edit + admin.

---

## 0. Onderliggende wet (geldt voor ELK item)

**Conversie-patroon** (de canonieke vorm — kopieer `members/index.html` / `admin/feedback.html`):
1. `<!DOCTYPE html><html lang="nl">` + eigen `<head>`.
2. In `<head>`: `<meta charset>`, `<meta viewport>`, `{% set noindex = … %}`, `{% set seo_title = … %}`, `{% include "_seo_head.html" %}`, Tailwind CDN, htmx, font-preconnect + Fraunces/Spline Sans/JetBrains Mono, `<link rel="stylesheet" href="/static/cosmic.css">`, de `<noscript>`-reveal-fallback, **+ favicon-partial + `theme-color` (zie §B/§detail)**.
3. `<body class="cosmic">` (forms met htmx: `<body class="cosmic" hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'>`).
4. Eerste include in body: `{% include "profiles/_cosmic_bg.html" %}` (puur CSS-achtergrond).
5. `<div class="wrap">` (publiek/404) of `<div class="wrap wrap--narrow">` (auth/forms/admin).
6. Header: `_cosmic_nav.html` waar een volledige nav past (404), of een **brand-only `<header class="c-head">`** met alleen `.brand` (auth-funnel) of brand + admin-`.link`s (admin).
7. Body-einde: `{% include "ai/_cosmic_canvas.html" %}` — **BEHALVE op 500.html** (geen JS dat kan falen als de app stuk is).

**Verboden:** tweede look, nieuwe fonts, losse hex-kleuren, `extends "base.html"` op een te-kosmiseren pagina, route-/service-/security-gedrag wijzigen, motion zonder `prefers-reduced-motion`-doving (globaal blok bestaat al; `data-reveal` valt onder `<noscript>`-fallback).

**NIET aanraken:** `VERSION`, `CHANGELOG.md`, `requirements.txt`, engine/AI-logica, en alle reeds-kosmische pagina's: `index.html`, `_cosmic_nav.html`, `members/*`, `profiles/{public,_photo_upload,_photo_ring,_emphasis_choice}.html`, `/projecten`, `/welkom`, `/profiel/ai/bouwen`, `/ideeen`, `/roadmap`, `admin/feedback.html`, `admin/_feedback_row.html`, `_completeness.html`, `_row_deleted.html` (erven automatisch zodra `_status_inner` kosmisch is).

---

## A. WERKLIJST per pagina/area

### TEAM-AUTH — auth-funnel + foutpagina's (HOOGSTE prioriteit: elke wachtlijst-persoon raakt dit)

| # | Bestand | Kosmiseren naar | Functie die INTACT blijft | Componenten / microcopy |
|---|---------|-----------------|---------------------------|--------------------------|
| A1 | `auth/login_request.html` | standalone cosmic, `wrap--narrow`, brand-only `c-head`. noindex hardcoded via `_seo_head` (`noindex=true`). | `<form method="post" action="/login">`; hidden `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">` **exact deze attribuut-volgorde** (test-regex); `name="email" type="email" required maxlength="320"`; `value="{{ email|default('') }}"`; `{% if error %}`. | `.eyebrow` "Toegang" + `.headline` "Inloggen" + `.lede` (huidige uitleg-tekst). `<label class="field-label">`. input erft `.cosmic input` (géén class). knop `<button class="btn">Stuur inloglink</button>`. secundaire link "Nog geen lid? → /register" als `.btn--ghost btn--sm`. error → `.notice .notice--error` (§B). `autocomplete="email"` + `autofocus`. |
| A2 | `auth/login_sent.html` | standalone cosmic, gecentreerd in `wrap--narrow`. | `{{ email }}`-interpolatie; link → `/login`. **Anti-enumeratie-zin LETTERLIJK behouden** ("Als … bekend is en is goedgekeurd …") — veiligheidstekst, niet cosmetisch; niet stelliger maken. | `.headline` "Kijk in je e-mail", `.lede` met `{{ email }}` in `.muted`/`<b>`. "Nieuwe link aanvragen" → `.btn--ghost btn--sm`. |
| A3 | `auth/login_error.html` | standalone cosmic, gecentreerd. | `{{ reason|default("Deze inloglink is ongeldig.") }}` (router levert 3 varianten); link `/login`. | `.headline` "Inloggen lukte niet", `.lede` = reason. CTA `<a class="btn" href="/login">Nieuwe inloglink aanvragen</a>`. |
| A4 | `auth/register.html` | standalone cosmic, `wrap--narrow`, brand-only header. | `<form method="post" action="/register">`; hidden csrf (exact); `name="name" maxlength="120"` + `name="email" type="email" required maxlength="320"`; beide `value="{{ …|default('') }}"`; `{% if error %}`. | `.eyebrow` "Aanmelden" + `.headline` "Word lid" + `.lede`. 2× `<label class="field-label">`. knop `.btn` "Aanmelden". "Al lid? Inloggen → /login" als `.btn--ghost btn--sm`. error → `.notice--error`. `autocomplete="name"`/`"email"` + `autofocus` op eerste veld. |
| A5 | `auth/register_done.html` | standalone cosmic, gecentreerd. | `{{ email }}`; link `/`. | `.headline` "Bedankt voor je aanmelding", `.lede` met `{{ email }}`. "Terug naar start → /" als `.btn--ghost btn--sm`. |
| A6 | `404.html` | standalone cosmic, **volledige `_cosmic_nav`** (geeft bezoeker een uitweg; geen form/security-context). | `noindex`; gerenderd met `status_code=404` (puur presentatie). | `.headline` "Pagina niet gevonden", `.lede` — **"… of is niet (meer) zichtbaar voor jou" behouden** (dekt besloten-profiel). CTA `.btn`/`.link` → `/`. Mag `_cosmic_canvas`. |
| A7 | `500.html` | standalone cosmic, **MAXIMAAL SIMPEL**: alleen `_cosmic_bg` (puur CSS) + brand-only `c-head` + tekst + link. **GEEN** `_cosmic_canvas`-JS, **GEEN** `request.session`/DB-reads (kan renderen wanneer iets stuk is). | `noindex`; `status_code=500`. | `.headline` "Er ging iets mis", bestaande `.lede` behouden, link → `/` als `.btn`. |

### TEAM-FORMS — edit + admin (na auth: 1e ingelogde scherm = `/profiel/bewerken`)

| # | Bestand | Kosmiseren naar | Functie die INTACT blijft | Componenten / microcopy |
|---|---------|-----------------|---------------------------|--------------------------|
| F1 | `profiles/edit.html` | standalone cosmic-document (kopie van `admin/feedback.html`-patroon): `_seo_head` `noindex=true` `seo_title="Mijn profiel · dewereldvan.ai"`, `<body class="cosmic" hx-headers='{"X-CSRF-Token":"{{ csrf_token }}"}'>`, `_cosmic_bg`, brand-only header, `wrap--narrow`. De 2 reeds-kosmische secties (foto `_photo_upload` + `_emphasis_choice`) blijven; `.cosmic`-class op die `<section>` mag weg (body draagt hem). | **Hoofdform** (`action="/profiel/bewerken"`): hidden `csrf_token`-field BLIJFT (geen htmx). Alle `name`/`id`/`required`/`maxlength`/`value` van `display_name,bio,makes_summary,tags`. `for`↔`id` koppeling. **htmx CRUD**: offering-form `hx-post="/profiel/offering"` `hx-target="#offering-list"` `hx-swap="beforeend"` `hx-on::after-request`; need-form idem `/profiel/need` `#need-list`; `#offering-error`/`#need-error` OOB-doelen; `<ul id="offering-list">`/`#need-list`. **Zichtbaarheid**: `name="visibility"` opties members/public + `selected`-logica, `name="consent"` checkbox + `checked`-logica, `hx-post="/profiel/zichtbaarheid"` `hx-target="#profiel-status"` `hx-swap="outerHTML"`. | `.eyebrow` "Mijn profiel · beheer" + `.headline` "Mijn profiel." + `.link` "Bekijk publieke pagina →". saved-banner → `.notice .notice--ok` "Je profiel is opgeslagen." (behouden, niet zweverig). error → `.notice--error`. completeness-wrapper → `.card`. labels → `.field-label`. submit-knoppen → `.btn` (hoofd) / `.btn--ghost btn--sm` (CRUD/zichtbaarheid). selects/inputs/textarea erven `.cosmic`. consent-rij tekst `.muted`. |
| F2 | `profiles/_offering_need_item.html` | kosmische rij (htmx-swap-doel, verschijnt in loop én bij elke add). | `id="{{ kind }}-{{ item.id }}"`, `hx-delete="/profiel/{{ kind }}/{{ item.id }}"`, `hx-target`, `hx-swap="outerHTML"`, `hx-confirm`. | rand `var(--line)`, titel `--text`, desc `--muted`, verwijder-knop `.text-link` (klein, ingetogen). |
| F3 | `profiles/_status_inner.html` | kosmisch (OOB-swap-doel na save/add/delete/visibility — moet matchen). | `id="profiel-status"` (via `_completeness`-wrapper), `profile.completeness`, `profile.visibility.value`. | progressbar → `.progress` + `.progress__fill` (§B); percentage `--gold`; zichtbaarheids-badge → `.chip` (cosmic.css:423). |
| F4 | `admin/queue.html` | standalone cosmic, **identiek aan `admin/feedback.html`** (zelfde header met `.link` → /admin/feedback + /admin/roadmap). Kies **kaart-lijst** (`.fb-list`-stijl) i.p.v. tabel → `_member_row` past natuurlijker als `<article>`. (richard-only, lagere prio, maar mee voor cohesie.) | `{% if pending %}`-loop; `noindex`; `_member_row.html` include. | `.eyebrow` "Beheer", `.headline` "Aanmeldingen.", `.lede`. lege staat → `.constellation-empty` + `✦`-spark. |
| F5 | `admin/_member_row.html` | kosmisch (htmx-swap-doel). **Top-level element-type moet matchen met F6.** | `id="member-{{ member.id }}"`; 3× `hx-post` (`/approve`,`/reject`,`/suspend`); `hx-target="#member-{{ member.id }}"`; `hx-swap="outerHTML"`; `hx-confirm`; status-conditionals (pending/approved/else); `{% if message %}`. | status-badge → `.chip` + modifier (`.chip--pending/--ok/--warn`, §B); approve → `.btn--sm`; weiger/schors → `.btn--ghost btn--sm`. |
| F6 | `admin/_member_gone.html` | kosmisch; **zelfde top-level element-type als F5** (beide `<article>` als F4 kaart-lijst is, anders beide `<tr>`). | swap-semantiek. | tekst "Dit lid bestaat niet meer" → `.muted`. |

### TEAM-DETAIL — assets + e-mails + microcopy (parallel; bezit cosmic.css)

| # | Bestand/area | Actie | Functie die INTACT blijft |
|---|--------------|-------|----------------------------|
| D1 | `app/static/favicon.svg` (+ `.ico`-fallback) **[nieuw asset]** | kosmisch favicon: donkere `#04040e` achtergrond + gouden `✦`/punt (`--gold #f6cd86`), 1-op-1 op `.brand .dot`. | additief; StaticFiles-mount serveert `/static/` al. |
| D2 | `app/templates/_favicon.html` **[nieuw partial]** | DRY-bron: `<link rel="icon" …>` + `<meta name="theme-color" content="#04040e">`. Wordt geïnclude in `<head>` van: `base.html`, `index.html`, `members/index.html`, `_seo_head`-consumers (alle cosmic `<head>`s incl. de nieuw-geconverteerde auth/edit/queue). | puur `<head>`-additie; raakt geen SEO-gating. |
| D3 | `og-default.png` **[nieuw asset, 1200×630]** + home/leden | kosmische nebula + wordmark `dewereldvan.ai`. Zet op `index.html` + `members/index.html`: `{% set og_image = base_url ~ "/static/og-default.png" %}` (absolute URL; `base_url` bestaat). `twitter:card` wordt dan automatisch `summary_large_image`. | OG blijft onderdrukt bij `noindex` (geen unfurl-datalek op besloten pagina's) — alleen de 2 publieke pagina's. |
| D4 | `index.html:37` microcopy | `{{ member_count }} MAKER{{ 'S' if member_count != 1 else '' }}` (eyebrow is uppercase → enkel de `S` togglen). | signal-gating (`member_count > 0`) ongewijzigd. **Test D4 in §D verplicht mee.** |
| D5 | `profiles/_cosmic_bg.html:6` | `<canvas id="stars" aria-hidden="true">`. | JS selecteert op `#stars` — `aria-hidden` raakt functie niet. |
| D6 | `emails/*` (`_base`, `magic_link`, `approval`, `admin_notify`) | **GEEN WERK** — reeds kosmisch, inline-CSS, table-layout, Gmail-fallback bgcolor, preheader. Wachtlijst-mails zijn al verzorgd. Alleen verifiëren bij oplevering. | — |

---

## B. CSS-SPEC — minimale nieuwe cosmic.css-classes (bovenop tokens)

Alles onder `.cosmic`-scope, alleen bestaande tokens (`--violet/--cyan/--gold/--text/--muted/--line/--card/--bg-1`). Geen nieuwe hex/font. **Totaal ≤ ~30 regels.** Eigenaar = TEAM-DETAIL.

| ID | Naam | Gedrag | Waarom (en bestaat NIET al — geverifieerd) |
|----|------|--------|--------------------------------------------|
| **C1** | `.cosmic .notice` + `.notice--error` + `.notice--ok` | Ingetogen melding-blok: `border:1px solid var(--line)`; `border-radius`; padding; tekst `var(--text)`. `--error`: linker-accent/rand zachte variant van `--violet`/`--gold` (GEEN knal-rood `bg-red-50`), tekst `var(--text)`, label `var(--muted)`. `--ok`: zacht goud-accent. Gebruik `role="alert"` op de error-instantie in de template. | grep bevestigt: géén `.cosmic .notice/.alert/.callout`. Auth-error (A1/A4) + edit saved/error (F1) hebben dit nodig; nu Tailwind rood/emerald = stijlbreuk. |
| **C2** | `.cosmic a:focus-visible, .cosmic .btn:focus-visible` | `outline: 2px solid var(--cyan); outline-offset: 2px;` | grep toont focus-visible op `.cnav__link`/`.member-star`/widgets, maar **niet** generiek op `.btn`/`a`. A11y-must voor de toetsenbord-funnel (auth knoppen + secundaire links). ~3 regels. |
| **C3** | `.cosmic .progress` + `.progress__fill` | track `background:var(--line)`, radius, hoogte ~6px; fill goud/violet-gradient (hergebruik bestaande knop-gradient-tokens), `width` via inline `style="width:{{ pct }}%"`. | F3 completeness-bar; nu Tailwind `bg-slate-200`/`bg-emerald-500`. ~6 regels. |
| **C4** | `.cosmic .chip--pending / --ok / --warn / --muted` | modifiers op bestaande `.chip` (cosmic.css:423): token-getinte rand+tekst per status (pending=violet, ok=gold/cyan, warn=zacht, muted=`--muted`). | F5 admin status-badge + F3 zichtbaarheids-badge; vermijdt inline-kleur-herhaling. ~6 regels. |

**Secundaire links**: GEEN nieuwe class — gebruik `.btn--ghost btn--sm` (consistent met `_cosmic_nav`). De bestaande `a.link` is gescopet als `.cosmic .c-head a.link` (cosmic.css:170) en pakt buiten `.c-head` niet; daarom auth-secundaire links via `.btn--ghost btn--sm`, niet `.link`.

**Hergebruik (bestaat, geverifieerd):** `.wrap`/`.wrap--narrow`, `.c-head`, `.brand`+`.dot`, `.cnav`, `.eyebrow`, `.headline`, `.lede`, `.section-title`, `.btn`/`.btn--ghost`/`.btn--sm`, `.cosmic input/textarea/select` (auto via element-selector — géén class op `<input>`), `label.field-label`, `.muted`, `.text-link`, `.card`, `.chip`/`.chips`, `.constellation-empty`(+spark), `.fb-list`. Achtergrond via `profiles/_cosmic_bg.html`.

---

## C. FILE-OWNERSHIP-MATRIX (disjunct — geen bestand bij 2 teams)

| Team | Bezit (mag bewerken) |
|------|----------------------|
| **TEAM-AUTH** | `app/templates/auth/login_request.html`, `auth/login_sent.html`, `auth/login_error.html`, `auth/register.html`, `auth/register_done.html`, `app/templates/404.html`, `app/templates/500.html` |
| **TEAM-FORMS** | `app/templates/profiles/edit.html`, `profiles/_offering_need_item.html`, `profiles/_status_inner.html`, `app/templates/admin/queue.html`, `admin/_member_row.html`, `admin/_member_gone.html` |
| **TEAM-DETAIL** | `app/static/cosmic.css` (**alle gedeelde CSS — C1-C4 hier, andere teams consúmeren alleen**), `app/templates/emails/*` (alleen verifiëren), `app/static/favicon.svg`, `app/static/og-default.png`, `app/templates/_favicon.html` (nieuw), `app/templates/base.html` (favicon/theme-color-include), `app/templates/index.html` (D4 microcopy + D3 og_image), `app/templates/members/index.html` (D3 og_image + favicon-include), `app/templates/profiles/_cosmic_bg.html` (D5 aria-hidden) |

**Volgorde-afhankelijkheid:** TEAM-DETAIL levert **C1-C4 + `_favicon.html` eerst** (TEAM-AUTH/FORMS hebben `.notice`/`.progress`/`.chip--*` + de favicon-partial nodig). AUTH en FORMS draaien daarna parallel (disjuncte bestanden). `members/index.html` raakt zowel DETAIL (og_image, favicon) als niemand anders → blijft bij DETAIL.

---

## D. TEST-SPEC

**Aanpassen (lichte-tekst/copy-asserts die de regressie cementeren):**

| Test | Nu | Wijzig naar | Reden |
|------|----|-------------|-------|
| `tests/test_home.py:182` | `assert "1 MAKERS" in resp.text` | `assert "1 MAKER" in resp.text` **en** `assert "1 MAKERS" not in resp.text` | D4 enkelvoud-fix; `_seed_public(...,1)` seedt exact 1. `test_home.py:175` (`"MAKERS" not in` bij 0) blijft kloppen (blok verborgen). |

**Geen wijziging nodig (geverifieerd):**
- `test_app_smoke.py` — CSRF-regex `name="csrf_token" value="([^"]+)"` op `/login`+`/register`: hidden-field-fragment blijft letterlijk → groen. Statuscode-asserts `/admin/queue` (200, nav-path) → puur status/URL.
- `test_ledenpagina_smoke.py:268` + `tests/_route_helpers.py:46-53` — accepteren `X-CSRF-Token` (hx-headers op body, zoals feedback.html) **of** hidden field → conversie van edit.html naar body-hx-headers blijft groen.
- `test_nav_integration.py` — admin-rol nav-gating ongewijzigd.
- Geen test assert op specifieke Tailwind-klassen van auth/admin/edit (alleen `test_home.py:104` assert `"text-slate-900" not in body` op de **al-kosmische** home — blijft kloppen).

**Toevoegen (zelfde sessie — bewaakt de regressie):**

| Nieuwe smoke | Assertie |
|--------------|----------|
| T1 auth cosmic | `GET /login`, `/register` → status 200 + `'class="cosmic"' in body` + `"text-slate-900" not in body` + `'name="csrf_token"' in body`. |
| T2 auth-eindpunten cosmic | render `login_sent`/`register_done` (via flow of directe call) → `class="cosmic"` + anti-enumeratie-zin nog aanwezig in `login_sent`. |
| T3 404/500 cosmic | geforceerde 404 (onbekende route) → status 404 + `class="cosmic"` + `noindex`. 500-render → `class="cosmic"` + GEEN `_cosmic_canvas`/`#stars`-JS-include (assert `'id="stars"' not in body` op 500). |
| T4 forms cosmic | `GET /profiel/bewerken` (ingelogd) → 200 + `class="cosmic"` + htmx-targets `id="offering-list"`,`id="need-list"`,`id="profiel-status"` aanwezig + csrf (hidden óf hx-header). |
| T5 admin cosmic | `GET /admin/queue` (admin) → 200 + `class="cosmic"`. |
| T6 assets | `GET /static/favicon.svg` → 200; `GET /static/og-default.png` → 200; home/leden-HTML bevat `og:image` met `/static/og-default.png` (publiek) en auth/edit/queue NIET (noindex → geen OG). |

**Kwaliteitspoort (autonoom na bouw):** `pytest` volledig groen + app boot-check (alle 7 auth/foutpagina's + edit + queue renderen zonder `base.html`-block-mismatch). Mobiel + toetsenbord + a11y (labels, `focus-visible` via C2), en lege/fout/succes-staten geverifieerd per form. Eindig niet voordat de suite groen is.

---

## Oplevervolgorde (funnel-prioriteit)
1. **TEAM-DETAIL**: C1-C4 in cosmic.css + `favicon.svg` + `_favicon.html` + `theme-color` → unblockt AUTH/FORMS.
2. **TEAM-AUTH**: A1-A7 (de uitnodig-funnel + landingen). Parallel met FORMS.
3. **TEAM-FORMS**: F1-F6 (1e ingelogde scherm + admin).
4. **TEAM-DETAIL** afronding: D3 og-default.png + og_image op home/leden, D4 microcopy + test, D5 aria-hidden, D6 e-mail-verificatie.
5. Tests aanpassen (D-tabel) + T1-T6 toevoegen → suite groen → boot-check.
