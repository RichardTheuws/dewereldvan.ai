---
status: SHIPPED (v0.10.0, 2026-06-18 — geïmplementeerd + adversarieel geverifieerd, 277 tests groen)
title: Levende profielbouw — autoritair bouwcontract
version: 1.0.0
date: 2026-06-18
supersedes: docs/VISION-profielbouw.md (vision → dit is de uitvoeringsspec)
owners: [backend-team, kern-team, css-team]
---

# SPEC — Levende profielbouw (BUILD-CONTRACT)

> **Eén levende flow**: tekst → het profiel materialiseert zich live in de echte
> kosmische profielvorm → daarna **volledig inline** bijschaven. Geen chat-ping-pong,
> geen aparte draft-preview, geen apart bewerk-formulier. Eén kosmische look
> (`cosmic.css`, STYLEGUIDE.md), eenvoudige directe NL-microcopy.

Dit contract is **autoritair**. Drie teams bouwen er onafhankelijk tegen (zie
§D file-ownership). De **engine** (`app/services/ai_profile.py` kernlogica,
`ai_conversation.py`, `app/ai/*`, models, migraties) wordt **niet gewijzigd** —
alleen hergebruikt. `VERSION`, `CHANGELOG.md`, `requirements.txt` worden door de
orchestrator beheerd — **niemand raakt die aan**.

## Ruggengraat van het ontwerp (gekozen synthese)

- **Backbone = best-craft**: één SSE-stream draait `stream_turn` (live redeneren) →
  daarna in dezelfde handler `finalize_draft` + persist → emit **per-veld
  `f-*`-events** die de profielvorm sectie-voor-sectie materialiseren. Eén
  verbinding, geen tweede knop nodig.
- **Robuustheid/AVG/a11y = robust-avg-a11y**: de flow eindigt **nooit** kapot.
  Materialisatie is gepersisteerd vóór elke swap → herladen rendert idempotent uit
  DB-staat. Refusal/timeout/exception → nette melding, vorm blijft bruikbaar
  (lege velden vallen terug op "vul aan"). Alle inline-edit is toetsenbord- en
  screenreader-bedienbaar; `prefers-reduced-motion` dooft alle motion; eigendoms-
  check + URL-guard + CSRF + autoescape op elke nieuwe route.
- **Reuse-eenvoud = minimal-reuse**: per-veld endpoints delegeren naar bestaande
  `profile_service`-bouwstenen; alleen drie dunne nieuwe service-helpers
  (`update_offering`, `update_need`, `profile_link_service`). `_persist_draft`
  verhuist naar een gedeelde service-functie zodat stream en (overgangs)route
  één bron delen.

## Beslissingen die alle teams binden

1. **Nieuwe pagina** `app/templates/ai/live.html` vervangt `ai/build.html` als
   respons van `GET /profiel/ai/bouwen`. Standalone cosmic-document (extend
   `base.html` NIET): herhaalt zelf htmx 2.0.4 + htmx-ext-sse 2.2.2 + Tailwind CDN
   + fonts + `/static/cosmic.css` + `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'`
   op `<body class="cosmic">` + `<meta name="robots" content="noindex">`
   (exact zoals huidige `build.html` head/body).
2. **`maak-draft`-logica verhuist de stream in** en wordt hernoemd weergegeven aan
   het profiel. De oude route `POST /profiel/ai/maak-draft` blijft **bestaan als
   thin wrapper** (rendert de levende vorm i.p.v. `_draft_preview.html`) tot de
   stream-variant groen test, dan verwijdert kern-team hem. Geen twee schrijfpaden
   die divergeren: beide roepen `profile_service.persist_draft(...)` aan.
3. **`POST /profiel/ai/draft/bewerken` vervalt** — vervangen door per-veld endpoints.
4. **Reorder van offerings/links = OUT OF SCOPE** voor v1. Posities volgen
   aanmaak-volgorde; de engine reconcilieert op positie. Niet breken. (Latere
   `PATCH …/reorder` is een aparte spec.)
5. **Onzekerheids-markers zijn transient UI-staat, GEEN DB-kolom** (datamodel is
   bevroren, geen migratie). Heuristiek: leeg veld → "vul aan"; AI-gevuld veld
   waar `profile.ai_enriched` true → zachte "afgeleid"-marker (alleen op
   headline + seeking, de meest-geïnterpreteerde velden). "Klopt"/edit verwijdert
   de marker voor die render. Bij reload tonen AI-velden de marker opnieuw —
   bewust (overzicht "nog te checken"), nooit blokkerend.

---

## A. ROUTE-CONTRACT (backend-team + kern-team)

Alle routes onder `require_member` (ingelogd + approved). CSRF via `hx-headers`
(X-CSRF-Token). Alle responses Jinja-autoescaped. URL-velden door de bestaande
`safe_url`-filter/guard (alleen `http`/`https`; `javascript:` → leeg, geen XSS).
**Eigendoms-check verplicht** op elke `{id}`: het object hoort bij
`member.profile`, anders **404** (spiegelt `remove_offering`/`remove_need`).
`recompute_completeness` na elke mutatie + OOB `#profiel-status`-fragment.

### A.0 — Gewijzigde levende-flow / SSE-endpoints (kern-team bezit de router)

| Methode | Pad | Request | Respons | Service |
|---|---|---|---|---|
| GET | `/profiel/ai/bouwen` | — | `ai/live.html` (de profielvorm uit **DB-staat**; idempotent herstel) | `profile_service.get_or_create_profile`, `photo_service.photo_or_initials` |
| POST | `/profiel/ai/bericht` | `message: str` | `ai/_materialize_stream.html` (SSE-host; **geen** user-bubbel — input is geen chat) | `ai_conversation.append_turn` + `ai_service.check_enrich_rate_limit` (rate-limit/lege input/AI-uit-takken ongewijzigd, maar render in `#denkpaneel`) |
| GET | `/profiel/ai/stream` | — | `text/event-stream` (zie §B.SSE) | `ai_service.stream_turn` → `ai_service.finalize_draft` → `profile_service.persist_draft` → per-veld slot-render |
| POST | `/profiel/ai/cover` | — | `ai/_cover.html` (ongewijzigd) | `cover_prompt` + `ImageGenerator` |
| POST | `/profiel/ai/publiceren` | `visibility: str`, `consent: str` | success → **303** `/leden/{slug}`; `ConsentRequired` → swap melding in `#publiceren` | `visibility_service.change_visibility` (consent voor public), `ai_conversation.clear_turns` |
| POST | `/profiel/ai/opnieuw` | — | **303** `/profiel/ai/bouwen` (AVG-reset: turns + ai_enriched + ai_source_text + cover) | `ai_conversation.clear_turns` |
| POST | `/profiel/ai/maak-draft` | — | **OVERGANG**: rendert `ai/_live_form.html` in `#profielvorm` (i.p.v. `_draft_preview.html`); verwijderen zodra stream-variant groen test | `profile_service.persist_draft` |

**SSE-handler (`GET /profiel/ai/stream`) gedragscontract** (kern-team):
- Fase 1 ongewijzigd: `reasoning`/`fetch`/`delta`-events, exact dezelfde
  escaping/wall-clock-timeout (`CHANNEL_TIMEOUT_SEC=120` begrenst nu stream_turn
  **én** finalize samen). `delta` gaat naar de "AI schrijft…"-regel in het
  reasoning-paneel (geen losse chat-bubbel).
- Assistant-turn wordt **vóór** het overgaan naar Fase 2 gepersisteerd
  (`append_turn` + `commit`) — `finalize_draft` ziet de complete history.
- Fase 2 (na stream_turn, in dezelfde threadpool-context):
  `finalize_draft(messages)` → `profile_service.persist_draft(...)` → `db.refresh(profile)`.
  Daarna **per veld** een uniek-benoemd event met het serverside-gerenderde
  slot-fragment (zie §B.SSE-tabel). Korte serverside `time.sleep(≤0.12)` tussen
  events voor de choreografie (begrensd door wall-clock-vangnet).
- Faal-takken (nooit kapotte vorm): `EnrichmentRefused` / `EnrichmentRateLimited` /
  exception / timeout-vóór-finalize → emit `done` met een nette melding-payload in
  `#denkpaneel`; de profielvorm blijft in placeholder/vorige staat. `db.rollback()`
  bij finalize-fout.

### A.1 — Per-veld profile-patch (headline/bio/seeking/tags) — backend-team

| Methode | Pad | Request | Respons | Service |
|---|---|---|---|---|
| GET | `/profiel/ai/veld/{naam}/bewerken` | `naam ∈ {headline,bio,seeking,tags}` | `ai/slots/_{naam}_edit.html` (mini-form) | — (render uit profile) |
| GET | `/profiel/ai/veld/{naam}` | idem | `ai/slots/_{naam}.html` (lees-slot; voor Esc/cancel) | — |
| PATCH | `/profiel/ai/veld/headline` | `value` (≤200) | `ai/slots/_headline.html` + `#profiel-status` OOB | `profile.headline = value or None`; `recompute_completeness` |
| PATCH | `/profiel/ai/veld/bio` | `value` (≤4000) | `ai/slots/_bio.html` + OOB | `profile.bio = value or None`; `recompute_completeness` |
| PATCH | `/profiel/ai/veld/seeking` | `value` (≤2000) → need[0] | `ai/slots/_seeking.html` + OOB | replace eerste Need (clear+`_make_need` of `update_need`); `recompute_completeness` |
| PATCH | `/profiel/ai/veld/tags` | `value` (komma-gescheiden) | `ai/slots/_tags.html` + OOB | `profile_service.set_tags`; `recompute_completeness` |
| POST | `/profiel/ai/veld/{naam}/bevestig` | — | `ai/slots/_{naam}.html` **zonder** marker | geen waarde-wijziging; alleen marker-loze render |

Validatie: lege verplichte input → lees-slot terug in "vul aan"-staat (geen 500).
Te lange input → server-side afkappen (maxlength), nette swap. `naam` buiten de set
→ 404.

### A.2 — Offerings (projecten) per-veld CRUD — backend-team

| Methode | Pad | Request | Respons | Service |
|---|---|---|---|---|
| POST | `/profiel/ai/offering` | `title`, `description`, `url`, `image_url` (alle optioneel; minstens leeg-template) | `ai/slots/_offering_card.html` (append `beforeend` in `#slot-projects .grid`) + OOB status | `profile_service.add_offering` + `update_offering` voor url/image_url |
| GET | `/profiel/ai/offering/{id}/bewerken` | — | `ai/slots/_offering_edit.html` (`#offering-{id}` outerHTML) | eigendoms-check |
| GET | `/profiel/ai/offering/{id}` | — | `ai/slots/_offering_card.html` (cancel) | eigendoms-check |
| PATCH | `/profiel/ai/offering/{id}` | `title`, `description`, `url`, `image_url` | `ai/slots/_offering_card.html` (`#offering-{id}` outerHTML) + OOB | **NIEUW** `profile_service.update_offering` (titelwijziging via `offering_slug.rename_to` + `ensure_slug`, 301-veilig) |
| DELETE | `/profiel/ai/offering/{id}` | — | leeg (200, kaart verdwijnt) + OOB status | `profile_service.remove_offering` |

### A.3 — ProfileLink (rollen, kind=affiliation) — volledige CRUD — backend-team

| Methode | Pad | Request | Respons | Service |
|---|---|---|---|---|
| POST | `/profiel/ai/rol` | `label`, `url`, `description`, `image_url` | `ai/slots/_role_card.html` (append `beforeend` in `#slot-roles .grid`) + OOB | **NIEUW** `profile_link_service.add` (kind=affiliation, position=len) |
| GET | `/profiel/ai/rol/{id}/bewerken` | — | `ai/slots/_role_edit.html` (`#role-{id}`) | eigendoms-check |
| GET | `/profiel/ai/rol/{id}` | — | `ai/slots/_role_card.html` (cancel) | eigendoms-check |
| PATCH | `/profiel/ai/rol/{id}` | `label`, `url`, `description`, `image_url` | `ai/slots/_role_card.html` (`#role-{id}` outerHTML) + OOB | **NIEUW** `profile_link_service.update` |
| DELETE | `/profiel/ai/rol/{id}` | — | leeg (200) + OOB | **NIEUW** `profile_link_service.remove` |

### A.4 — Need per-veld (naast seeking[0]) — backend-team

`seeking` (§A.1) muteert de **primaire** Need. Voor expliciete losse needs (visie:
meerdere) levert backend-team **`profile_service.update_need(db, profile, id, *, title, description)`** (eigendoms-check, `recompute_completeness`).
Endpoints `POST/PATCH/DELETE /profiel/ai/need[/{id}]` zijn **optioneel v1** (alleen
bouwen als de vorm meerdere needs toont); de service-helper wordt sowieso geschreven
en getest zodat A.1-seeking erop kan leunen.

### Nieuwe service-functies (backend-team, in `app/services/`)

- `profile_service.update_offering(db, profile, offering_id, *, title=None, description=None, url=None, image_url=None) -> Offering | None` — eigendoms-check; bij titelwijziging `offering_slug.rename_to` + altijd `ensure_slug`; URL-velden door `safe_url`-guard; `recompute_completeness`; `None` bij niet-eigendom (route → 404).
- `profile_service.update_need(db, profile, need_id, *, title, description=None) -> Need | None` — analoog.
- `profile_service.persist_draft(db, profile, draft, *, source_messages)` — **verhuisde** `_persist_draft` (identieke logica) naar de service-laag, zodat stream + overgangsroute één bron delen. Kern-team importeert dit; backend-team bezit de definitie. **Coördinatiepunt** (zie §F).
- **Nieuw bestand** `app/services/profile_link_service.py`: `add(db, profile, *, label, url, description, image_url) -> ProfileLink` (kind=affiliation, position=len), `update(db, profile, link_id, *, label, url, description, image_url) -> ProfileLink | None` (eigendoms-check), `remove(db, profile, link_id) -> bool`. Allen `recompute_completeness` (rollen tellen niet mee in score, maar consistent flushen) + `db.flush()`.

Validatie-schema's (backend-team, in `app/schemas/ai_profile.py`): `FieldForm(value)`,
`OfferingPatchForm(title, description, url, image_url)`, `ProfileLinkForm(label, url, description, image_url)` (Pydantic, lengtes conform model; URL door `safe_url`).

---

## B. TEMPLATE-CONTRACT (kern-team)

Kern-team bezit `app/templates/ai/*` + de nieuwe profielvorm-partials. De lees-slots
**includen waar mogelijk de bestaande cosmic-card-partials** (`_cosmic_project_card.html`,
`_cosmic_link_card.html`, `_cosmic_tags.html`) zodat de profielvorm **byte-identiek**
is aan `profiles/view.html` (geen tweede look). Alleen de edit-wrappers + markers
zijn nieuw.

### B.1 — Nieuwe templates + element-ID's

| Bestand | Element-ID('s) | Inhoud |
|---|---|---|
| `ai/live.html` | `#invoer`, `#denkpaneel`, `#profielvorm`, `#publiceren`, `#materialisatie-status` (`aria-live="polite"`), `#profiel-status` | Standalone cosmic-document. `.wrap.wrap--narrow.{{emphasis_cls}}`. Bevat invoer-dok (textarea + "Bouw mijn profiel" → `POST /profiel/ai/bericht`, `hx-target="#denkpaneel" hx-swap="innerHTML"`), de levende profielvorm, foto-upload + emphasis-keuze in identity-sectie, publiceer-dok, "Opnieuw beginnen". |
| `ai/_materialize_stream.html` | `#sse-{sid}` (host), `[data-reasoning]`, `[data-answer]` | Variant van `_message_sent.html` **zonder** user-bubbel. `hx-ext=sse sse-connect=/profiel/ai/stream sse-close=done`. `sse-swap`-bindings: `reasoning`/`fetch` → reasoning-paneel; `delta` → "AI schrijft…"-regel; zes `f-*`-events → slot-targets (zie B.SSE). Mini-`<script>` voor materialize-class-cleanup (uit `_message_sent.html`). Hergebruikt `ai/_reasoning_panel.html` ongewijzigd. |
| `ai/_live_form.html` | `#profielvorm` (wrapper), alle slot-ID's (zie B.2) | De bewerkbare profielvorm; spiegelt de `view.html`-macro-structuur (identity, bio, roles, projects, seeking) met emphasis-volgorde. Per sectie `data-reveal style="--d:Xms"`. Gebruikt de slot-partials. Includet `profiles/_photo_upload.html` + `profiles/_emphasis_choice.html` ongewijzigd. |
| `ai/slots/_headline.html` | `#slot-headline` | lees-slot kopregel (`h1.headline`), `.slot.slot--text`, klik-tot-edit + optionele marker |
| `ai/slots/_headline_edit.html` | `#slot-headline` | mini-form (`<input maxlength=200>`) |
| `ai/slots/_bio.html` | `#slot-bio` | lees-slot bio (`.lede`) |
| `ai/slots/_bio_edit.html` | `#slot-bio` | mini-form (`<textarea>`) |
| `ai/slots/_seeking.html` | `#slot-seeking` | lees-slot (`.seeking` gouden kaart) |
| `ai/slots/_seeking_edit.html` | `#slot-seeking` | mini-form (`<textarea>`) |
| `ai/slots/_tags.html` | `#slot-tags` | lees-slot (`.chips`, include `_cosmic_tags.html`) |
| `ai/slots/_tags_edit.html` | `#slot-tags` | mini-form (`<input>` komma-gescheiden) |
| `ai/slots/_roles.html` | `#slot-roles` | hele `.grid` van rolkaarten + "+ rol toevoegen" |
| `ai/slots/_role_card.html` | `#role-{id}` | één rolkaart (include `_cosmic_link_card.html`) + bewerk-affordance + `✕` |
| `ai/slots/_role_edit.html` | `#role-{id}` | mini-form (label/url/description/image_url) |
| `ai/slots/_projects.html` | `#slot-projects` | hele `.grid` van projectkaarten + "+ project toevoegen" |
| `ai/slots/_offering_card.html` | `#offering-{id}` | één projectkaart (include `_cosmic_project_card.html`) + bewerk-affordance + `✕` |
| `ai/slots/_offering_edit.html` | `#offering-{id}` | mini-form (title/description/url/image_url) |
| `ai/_publish_panel.html` | `#publiceren` | zichtbaarheid + consent + knop (uit publish-deel van `_draft_preview.html`); `ConsentRequired`-melding-slot |
| `ai/_status_oob.html` | `#profiel-status` (`hx-swap-oob`) | completeness-fragment, na elke mutatie OOB meegestuurd |

**Behouden ongewijzigd**: `ai/_reasoning_panel.html`, `ai/_cover.html`,
`ai/_cosmic_canvas.html`, `profiles/_cosmic_bg.html`, `profiles/_cosmic_tags.html`,
`profiles/_cosmic_link_card.html`, `profiles/_cosmic_project_card.html`,
`profiles/_photo_upload.html`, `profiles/_emphasis_choice.html`, `_feedback_affordance.html`.
**Vervalt uit de flow** (blijven bestaan tot overgangsroute weg is):
`ai/build.html`, `ai/_message_sent.html`, `ai/_chat_message.html`, `ai/_draft_preview.html`.

### B.SSE — Materialisatie-mechanisme (events + targets)

Eén SSE-verbinding, **unieke event-naam per slot** (htmx-sse bindt één swap-target
per event-naam per element — verifieer tegen het werkende drie-naam-patroon
`delta`/`reasoning`/`fetch` in `_message_sent.html`). Elk slot-`<div>` in
`_live_form.html` draagt `sse-swap="f-…"` + `hx-target="#slot-…" hx-swap="outerHTML"`.

| Event-naam | Target-ID | Fragment (serverside uit DB na `refresh`) |
|---|---|---|
| `reasoning` | `[data-reasoning]` (in `#denkpaneel`) | live thinking |
| `fetch` | `.reasoning__fetch` | per-link host ✓/✗ |
| `delta` | `[data-answer]` | "AI schrijft…"-tekst |
| `f-headline` | `#slot-headline` | `ai/slots/_headline.html` |
| `f-bio` | `#slot-bio` | `ai/slots/_bio.html` |
| `f-tags` | `#slot-tags` | `ai/slots/_tags.html` |
| `f-roles` | `#slot-roles` | `ai/slots/_roles.html` (hele grid) |
| `f-projects` | `#slot-projects` | `ai/slots/_projects.html` (hele grid) |
| `f-seeking` | `#slot-seeking` | `ai/slots/_seeking.html` |
| `done` | `#sse-{sid}` | leeg → host verdwijnt; reasoning-strip krijgt `.reasoning--settled`; `#materialisatie-status` aria-live: "Je profiel is opgesteld. Loop het na en pas aan waar nodig." |

Elk landend slot-fragment draagt op de wrapper `field--materializing` (blur-in);
mini-`<script>` (zoals `_message_sent.html`) zet `field--ready` na het keyframe.
`prefers-reduced-motion` → directe verschijning.

### B.2 — Klik-tot-edit-patroon per veldtype

Basis = veralgemenisering van `_emphasis_choice.html` (self-replacing `hx-swap=outerHTML`
op eigen ID). Elk slot heeft een **lees-fragment** en een **edit-fragment**; het
edit-fragment post terug naar het lees-fragment (één bron van waarheid, geen client-state).
**Geen contenteditable** (a11y/sanitisatie) — altijd echt `<form>` + echt `<input>/<textarea>`.

**Gedeeld a11y-contract per slot** (kern-team):
- Lees-element: `tabindex="0"`, `role="button"`, `aria-label="Bewerk {veld}"`, zichtbare
  potlood/✦-affordance (`.field-edit-hint`). Activatie: `hx-trigger="click, keyup[key=='Enter']"`.
- Edit-fragment: focus bij swap-in (`hx-on::after-swap` → `.focus()`); **Esc** = annuleren
  (`hx-get` lees-slot, geen persist); zichtbare **Bewaar**/**Annuleer** (`.btn--sm`) naast
  het form (muis + reduced-motion). Tekstvelden mogen op **blur autosave** (alleen bij
  gewijzigde, niet-lege waarde voor verplichte velden; lege optionele waarde = geldige wis).

| Veldtype | Lees-slot | Edit-control | GET-edit | Persist | Terug-swap |
|---|---|---|---|---|---|
| Kopregel | `#slot-headline` `.slot--text` | `<input maxlength=200>` | `/profiel/ai/veld/headline/bewerken` | `PATCH /profiel/ai/veld/headline` | `_headline.html` |
| Bio | `#slot-bio` `.slot--text` | `<textarea>` | `…/veld/bio/bewerken` | `PATCH …/veld/bio` | `_bio.html` |
| Seeking | `#slot-seeking` | `<textarea>` | `…/veld/seeking/bewerken` | `PATCH …/veld/seeking` | `_seeking.html` |
| Tags | `#slot-tags` | `<input>` komma | `…/veld/tags/bewerken` | `PATCH …/veld/tags` | `_tags.html` |
| Project | `#offering-{id}` | mini-form title/description/url/image_url | `/profiel/ai/offering/{id}/bewerken` | `PATCH /profiel/ai/offering/{id}` | `_offering_card.html` |
| Rol | `#role-{id}` | mini-form label/url/description/image_url | `/profiel/ai/rol/{id}/bewerken` | `PATCH /profiel/ai/rol/{id}` | `_role_card.html` |
| Project toevoegen | knop in `#slot-projects` | — | — | `POST /profiel/ai/offering` | append `beforeend` |
| Rol toevoegen | knop in `#slot-roles` | — | — | `POST /profiel/ai/rol` | append `beforeend` |
| Project/rol verwijderen | `✕` op kaart | — | — | `DELETE …/{id}` | kaart `outerHTML` → leeg + OOB status |
| Foto | `#photo-ring` | bestaande `_photo_upload.html` drag-drop | — | bestaand `POST /profiel/foto` | `#photo-ring` outerHTML (`is-materializing`) |
| Emphasis | `#emphasis-choice` | bestaande `_emphasis_choice.html` | — | bestaand `POST /profiel/emphasis` | zichzelf |

### B.3 — Onzekerheids-marker-UX + microcopy (gewone, directe NL)

Server-side bepaald in het lees-slot (geen schema-wijziging):
- **Ontbrekend** (`None`/leeg waar inhoud hoort): `.slot--ask` (gouden accent-rand),
  microcopy + 1-tik opent direct edit. `aria-label="{veld}: nog leeg, klik om aan te vullen"`.
  - Kopregel: **"Nog geen kopregel — tik om er één te schrijven"**
  - Bio: **"Vertel kort wie je bent"**
  - Seeking: **"Waar zoek je naar?"**
  - Projecten/rollen leeg: **"Nog geen projecten — voeg er één toe"** / **"Nog geen rollen"**
- **Afgeleid** (AI-gevuld + `profile.ai_enriched`; alleen headline + seeking):
  `.uncertain` wrapper met gouden `.uncertain__dot` (✦ rechtsboven) + op hover/focus
  een mono-hintregel `.uncertain__hint`: **"Dit leidde ik af — klopt het?"** met twee
  1-tik-acties (`.uncertain__act`, `.btn--sm`):
  - **"Klopt"** → `POST /profiel/ai/veld/{naam}/bevestig` → marker-loze render.
  - **"Aanpassen"** → opent edit-form (`GET …/bewerken`).
- Na succesvolle save: subtiele `.photo-ring__msg--ok`-flits **"✦ bewaard"** (hergebruik).
- Onbereikbare links: al gemeld in de reasoning/fetch-strip (✗) — **geen** extra marker.

Verboden microcopy: zweverige taal ("je ster is verschenen"). Toegestaan: "Vul aan",
"Dit leidde ik af — klopt het?", "Klopt", "Aanpassen", "Bewaar", "Annuleer", "✦ bewaard".

---

## C. CSS-CONTRACT (css-team — bezit ALLEEN `app/static/cosmic.css`)

Alle nieuwe classes **binnen `.cosmic`-scope**, erven bestaande tokens
(`--violet/--cyan/--magenta/--gold/--text/--muted/--line/--card`) + fonts (Fraunces/
Spline Sans/JetBrains Mono). **Geen tweede look.** Alle motion **reduced-motion-safe**
(`@media (prefers-reduced-motion: reduce)` dooft blur/translate/scale → directe
verschijning; markers blijven zichtbaar, alleen animatie weg).

### Inline-edit-affordance
- `.slot` — klikbaar veld-wrapper: `position:relative`, `cursor:pointer`,
  `:focus-visible` cyan focus-ring (hergebruik input-focus-glow-token).
- `.slot--text` — tekstveld-variant.
- `.slot:hover` / `.slot:focus-visible` — subtiele lift + 1px `--line`→`--cyan`
  rand-fade (zoals `a.card:hover`), onthul `.field-edit-hint`.
- `.field-edit-hint` — klein potlood/✦-glyph rechtsboven, alleen zichtbaar op
  hover/focus.
- `.slot-edit` / `.field-edit` — compacte inline-form-container met dezelfde
  input-styling (`.cosmic input/textarea`).

### Onzekerheids-marker
- `.slot--ask` — lege-veld-invul-affordance: gouden accent-rand (stippel toegestaan)
  + ruimte voor de invul-microcopy in `--muted`/`--gold`.
- `.uncertain` — `position:relative` wrapper.
- `.uncertain__dot` — gouden ✦-stip, `position:absolute` rechtsboven.
- `.uncertain__hint` — dunne JetBrains-Mono regel (`--muted`/`--gold`), verschijnt
  op hover/focus van het slot.
- `.uncertain__act` — container voor de twee 1-tik-knoppen (leunt op `.btn--sm`).

### Veld-materialisatie
- `.field--empty` — placeholder-stijl (`--muted`), zachte glow; geen content-flash.
- `.field--materializing` + `@keyframes field-materialize` — veralgemeniseerde
  blur-in van `photo-materialize`: `opacity 0→1`, `filter: blur(8px)→0`,
  `transform: translateY(8px) scale(0.98)→none`.
- `.field--ready` — eind-staat (klik/hover normaal).
- `.materialize` mag als alias voor de generieke keyframe dienen indien handiger.

Bestaand (hergebruiken, niet herdefiniëren): `.wrap/.wrap--narrow`, `.emphasis-*`,
`.card/a.card:hover/.thumb/.grid`, `.seeking`, `.chips/.chip`, `.btn/.btn--ghost/--sm`,
`input/textarea/select` + `label.field-label`, `.photo-ring/.photo-ring--hero/.is-materializing`
(`@keyframes photo-materialize`), `.reasoning*/--settled`, `[data-reveal]`→`.cosmic.ready`,
`.bubble--*`, `.headline/.lede/.display-name/.section-title/.eyebrow`,
`.photo-ring__msg--ok`, `prefers-reduced-motion`.

---

## D. FILE-OWNERSHIP-MATRIX (disjunct — parallel bouwen zonder conflicten)

| Team | Bezit (schrijft) | Mag NIET aanraken |
|---|---|---|
| **backend-team** | `app/routers/profiles.py` (per-veld endpoints A.1–A.4 mits niet in ai_profile.py — zie §F), `app/services/profile_service.py` (`update_offering`, `update_need`, `persist_draft`), **nieuw** `app/services/profile_link_service.py`, `app/schemas/ai_profile.py`, `tests/test_inline_edit_*.py`, `tests/test_profile_link_service.py` | `app/templates/*`, `app/static/cosmic.css`, engine, models, migraties |
| **kern-team** | `app/routers/ai_profile.py` (SSE-handler Fase 2, `/bouwen`, `/bericht`, materialisatie, per-veld **route-handlers** die backend-services aanroepen), **alle** `app/templates/ai/*` (incl. `ai/live.html`, `ai/_materialize_stream.html`, `ai/_live_form.html`, `ai/slots/*`, `ai/_publish_panel.html`, `ai/_status_oob.html`), `tests/test_ai_living_flow.py` | `app/static/cosmic.css`, `app/services/*` (alleen importeren), engine, models, migraties, `profiles/view.html` (alleen lezen) |
| **css-team** | **ALLEEN** `app/static/cosmic.css` | al het overige |

**Router-eigendom-keuze**: om disjunct te blijven bezit **kern-team
`ai_profile.py`** (alle `/profiel/ai/*`-routes, incl. de per-veld inline-edit
handlers — want de profielvorm en zijn slots zijn kern-domein). **backend-team
bezit de service-laag + schema's + `profiles.py`** en levert de functie-signatures
die kern-team aanroept. Zo schrijven twee teams nooit hetzelfde bestand.

---

## E. TEST-CONTRACT (engine-mock-grens behouden)

Tests draaien op **SQLite in-memory**, **zonder Postgres**, **zonder API-key**.
Engine wordt gemockt op de **service-grens** (`monkeypatch.setattr(ai_service, "stream_turn"/"finalize_draft", …)`) — bestaande engine-unit-tests blijven
ongemoeid (`test_ai_profile_schema.py`, `test_ai_profile_imports.py`,
`test_image_generator.py`, `test_ai_profile_model.py`, `test_wait_ux_sse.py`).

**backend-team** (`tests/test_inline_edit_*.py`, `test_profile_link_service.py`):
- Per-veld PATCH headline/bio/seeking/tags: happy-path schrijft + `recompute_completeness`; lege verplichte input → "vul aan"-staat (geen 500); te-lang → afgekapt.
- `update_offering`: titelwijziging → `offering_slug.rename_to` aangeroepen (301-historie); url/image_url door `safe_url`-guard (`javascript:` geweigerd).
- `profile_link_service` add/update/remove: happy-path + **eigendoms-404** (vreemd id → 404, geen mutatie).
- Need-update happy + eigendoms-404.
- CSRF-header vereist (zonder → afgewezen).

**kern-team** (`tests/test_ai_living_flow.py`):
- `GET /profiel/ai/bouwen` rendert `ai/live.html` met de slot-ID's uit DB-staat (idempotent na materialisatie).
- `POST /profiel/ai/bericht` rendert `ai/_materialize_stream.html` (geen user-bubbel).
- SSE-stream (`finalize_draft` gemockt): success → emit `f-headline`…`f-seeking` + `done`; `EnrichmentRefused` / exception → `done` met melding, **geen kapotte vorm**, profielvorm-staat intact.
- Per-veld GET-edit → edit-fragment; PATCH → lees-slot terug (`outerHTML`, juiste ID).
- Marker-bevestig (`POST …/bevestig`) → lees-slot zonder marker.
- Materialisatie-route (overgang `maak-draft` zolang aanwezig) swap `#profielvorm`.
- Publiceren: success → 303 `/leden/{slug}`; `ConsentRequired` → melding in `#publiceren` (geen redirect).
- Inline-edit blur-zonder-wijziging → geen write; Esc → lees-slot zonder write.

**Snapshot/HTML-borg** (kern-team): de read-only slot-fragmenten dragen dezelfde
cosmic-classes als `profiles/view.html` (één look — assert classes op
headline/bio/roles/projects/seeking).

**css-team**: geen pytest; visuele borging = `prefers-reduced-motion` dooft elke
nieuwe keyframe (handmatige check + comment in cosmic.css).

---

## F. COÖRDINATIEPUNTEN (de enige cross-team-naden)

1. **`profile_service.persist_draft`** — backend-team levert de signature
   `persist_draft(db, profile, draft, *, source_messages) -> None` (verhuisde
   `_persist_draft`, identieke logica). Kern-team importeert die in `ai_profile.py`
   (stream Fase 2 + overgangsroute). **Afspraak**: backend-team committeert deze
   functie eerst (dag 1) zodat kern-team ertegen kan bouwen; tot dan importeert
   kern-team de oude `_persist_draft` als tijdelijke alias.
2. **Service-signatures A.1–A.4** — backend-team bevriest deze signatures (zie §A)
   vóór kern-team de route-handlers schrijft. Kern-team roept alleen aan, definieert niet.
3. **Slot-ID's + event-namen (§B.SSE/B.1)** — kern-team is eigenaar; css-team styling
   leunt op de classes (`.slot`, `.uncertain`, `.field--*`), niet op de ID's →
   geen naad met css.
4. **`profiles/view.html`** — blijft visueel ongewijzigd; als kern-team gedeelde
   `_*_inner`-includes wil extraheren, mag dat alleen include-refactor zijn (geen
   stijlwijziging) en valt onder kern-team-eigendom (templates).

---

**Verdict op het contract: PASS** — bouwbaar op de bestaande engine + htmx/SSE-
patronen zonder enige engine-, model- of migratiewijziging; drie teams werken
disjunct (services+schemas / ai-router+templates / cosmic.css) met exact vier
gecoördineerde naden (§F). Geen tweede look, AVG/a11y geborgd, nooit een kapotte
eindstaat.
