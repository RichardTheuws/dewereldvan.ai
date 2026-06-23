# Changelog

Alle noemenswaardige wijzigingen aan dit project worden hier vastgelegd.
Volgt [Keep a Changelog](https://keepachangelog.com/) en [SemVer](https://semver.org/).

## [0.88.2] - 2026-06-23
### Fixed — Onzichtbare kosmische pagina's: reveal-director ontbrak
- `/profiel/verbind` (connect) en de AVG-afscheidspagina (`profiles/deleted.html`) renderden met JS aan een
  **lege pagina**: ze gebruiken `data-reveal` (start op `opacity:0`) maar includen `ai/_cosmic_canvas.html` níét —
  de director die `body.ready` zet. Zonder director blijft alles onzichtbaar (de `<noscript>`-fallback dekt
  alleen JS-úít). Beide pagina's includen de director nu, conform de 28 andere kosmische pagina's. Ze krijgen
  meteen ook de levende sterrenhemel die ze misten.
- Regressie-test `tests/test_reveal_director.py`: scant álle templates en dwingt af dat elke volledige cosmic-
  pagina met `data-reveal` de reveal-director include — zodat dit type "blanco pagina" niet meer stil terugkeert.

## [0.88.1] - 2026-06-23
### Changed — Aankondigings-mail: nette aanhef + expliciete privacy-geruststelling
- De mail legt nu expliciet uit dat **je profiel pas zichtbaar wordt als je het zélf op openbaar zet** (12 van
  de 15 leden hebben nog geen publiek profiel — dit verlaagt de drempel en respecteert de privacy).
- De aanhef gebruikt de **voornaam** waar het een echte naam is, en valt netjes terug op een neutrale aanhef
  ("Er is veel nieuw.") bij placeholder-/e-mailprefix-namen (geen "Er is veel nieuw, herberttenhave.").

## [0.88.0] - 2026-06-23
### Added — Eenmalige features-aankondigings-mail naar de leden (dry-run-veilig)
- Kosmische HTML-mail (`emails/announcement.html` + `render_announcement`) die de nieuwe functies opsomt en
  uitnodigt om ze te proberen, ideeën in te sturen en mee te bouwen via GitHub. Eén feature-bron
  (`ANNOUNCEMENT_FEATURES`) voedt zowel de HTML als de tekst-fallback.
- Verzend-script `scripts/announce_features.py` — **dry-run is de default** (toont ontvangers + tekst, verstuurt
  niets); pas met `--send` gaat 'ie echt uit (Cloudflare-backend op M4). Per-ontvanger fail-safe; aanhef
  gepersonaliseerd. Ontvangers = goedgekeurde leden met e-mail.
- Mail visueel geverifieerd in de browser. 1040 tests groen.

## [0.87.0] - 2026-06-23
### Changed — Agenda-curatie vindt nu óók lokale, terugkerende meetups (slimmer)
- De curatie zocht vooral grote conferenties. Nu zoekt ze **bewust breed** naar lokale, terugkerende AI-meetups:
  Meetup.com-groepen per NL/BE-stad, bekende community-reeksen (Aimelo, PyData-chapters, GenAI/LLM-meetups,
  AI Tinkerers, …), en reeksen met een vaste cadans. De grondingsregel blijft hard (alleen uit echte pagina's).
- **Terugkerende meetups gaan nu óók automatisch live** wanneer ze zeker zijn: de auto-keur-poort accepteert
  naast een concrete datum ook een **gegronde cadans** (terugkerende frequentie + `cadence_note` uit de pagina)
  + locatie + hoge confidence. Zo belandden lokale meetups niet langer onnodig in de admin-queue.
- **Tests**: terugkerende meetup mét cadans + locatie → auto-live; zonder cadans (ongegrond) of met frequentie
  "eenmalig" → queue. 1040 groen.

## [0.86.0] - 2026-06-23
### Changed — Roadmap als écht cosmisch kanban + homepage-waardepropositie + agenda-approvals zichtbaar
- **Agenda-approvals zichtbaar**: een admin ziet nu op `/agenda` een banner ("N door de agent gevonden
  events wachten op je beoordeling → Beoordeel") die naar `/admin/agenda` linkt. De pending-kandidaten waren
  alleen via een directe URL te vinden; nu zijn ze in-context vindbaar.
- **Roadmap is nu een echt kosmisch kanban-bord**: vier vaste status-kolommen (Overwegen → Gepland → In
  aanbouw → Gelanceerd), óók de lege, elk met een status-getinte kop-gloed. Items zijn **cosmische notes**
  (status-dot, fase-tag, corner-spark, status-gekleurde accent-rand). Op mobiel een swipebare kanban
  (scroll-snap). Groepeert nu op **status** i.p.v. de verwarrende vrije `phase`-string.
- **Roadmap-inhoud verversd** (`scripts/seed_roadmap.py`, idempotent): stond nog op pre-pivot-inhoud (bv.
  "Events" onder Overwegen terwijl de agenda al live is). Nu de echte staat — **11 dingen gelanceerd**
  (AI-profiel uit een link, ontdekking, ledengids, matchmaking+intro's, MCP, agenda+RSVP, agenda-curatie,
  nieuws-briefing, tool-catalogus, ideeënbus, notificaties), 1 in aanbouw, 2 gepland, 2 in overweging.
  Community-gevoede (idee-gekoppelde) items blijven behouden.
- **Roadmap publiek + indexeerbaar**: de levende roadmap is transparant onderdeel van de waardepropositie
  (noordster), niet meer login-gated.
- **Homepage-waardepropositie**: nieuwe secties die vertellen **waarom** je een profiel maakt (één profiel,
  de agent werkt voor je), **wat er nu al kan** (4 feature-cards), **wat eraan komt** (link naar de publieke
  roadmap) en **hoe je meebouwt** (open project, GitHub, ideeën).
- **GitHub-repo-beschrijving** bijgewerkt naar de huidige realiteit (geen "teaser" meer).
- Alles binnen het kosmische concept (`docs/STYLEGUIDE.md`): indigo glas-notes, goud spaarzaam accent,
  Fraunces/JetBrains Mono, eenvoudige microcopy. 1039 tests groen; roadmap + homepage browser-geverifieerd.

## [0.85.0] - 2026-06-23
### Added — AI-agenda-curatie: vult de agenda met ECHTE events + keurt het zekere zelf goed
- De wekelijkse curatie (maandag, M4-cron) zoekt het web af naar aankomende **NL/BE AI-events & meetups** en
  plaatst ze: **zeker** (hoge confidence + gegronde datum + locatie) → direct **live** op de agenda; **twijfel**
  → `pending_review` in de nieuwe admin-queue `/admin/agenda`. In lijn met je keuze "AI cureert én keurt zelf
  goed wat ze zeker kan keuren".
- **Harde grondingsregel**: events komen UITSLUITEND uit echte event-pagina's (web_search + web_fetch op
  Opus 4.8), nooit uit model-geheugen — geen verzonnen datum/locatie. Bron-strategie: **web-search** (geen
  hand-onderhouden seed-lijst). `event_curation_service` spiegelt het bewezen `news_curation_service`-SDK-patroon
  exact (pause-loop, refusal-check, eigen `record_event_item`-tool, geen `messages.parse`).
- **Auto-keur-poort** (`auto_approvable`): confidence ≥ 85 én datum én locatie → live; anders pending.
  KILL-fallback: AI uit of een fout → lege lijst → niets gepubliceerd (nooit silent-publish bij twijfel).
- **Idempotent**: dedup op URL (`create_curated_event`) — een herhaalde run maakt geen dubbele events.
- **Admin-surface**: `/admin/agenda` (shortlist van twijfel-kandidaten) + één-klik goedkeuren/weigeren
  (htmx-swap, AuditLog `event_approved`/`event_rejected` — additieve enum-waarden, geen migratie).
- **Seintje**: na de run een best-effort Telegram-push naar de admins (hoeveel live, hoeveel wachten).
- **Cron**: `curate_events` toegevoegd aan `nightly-jobs.sh`, wekelijks op **maandag** (los van de nieuws-
  curatie op zondag zodat de twee AI-tool-loops elkaar niet kruisen).
- **Tests**: gegronde mapping, grondings-/drempel-poorten, `_parse_dt`, `auto_approvable`, live-vs-pending +
  dedup persist, pending-sortering, admin approve/reject + admin-only-gate, en dat een live AI-event publiek
  verschijnt maar een pending niet. 1037 groen.

## [0.84.0] - 2026-06-22
### Added — RSVP op de agenda (aanwezig / organiseert / spreekt) — de agenda wordt sociaal
- Elk lid kan zich per event aanmelden met één rol: **Ik ga / Ik organiseer / Ik spreek hier** (wederzijds
  exclusief, één rol per lid per event — her-kiezen = wijzigen, geen dubbele rij). De event-kaart toont nu de
  **telling** ("3 gaan") + de **namen van organisatoren/sprekers**, die linken naar hun publieke profiel —
  een echte graaf-knoop (geen aparte graaf-tabel). Anon ziet de telling + "Word lid om je aan te melden".
- **Model**: nieuwe tabel `event_attendance` (`EventAttendance`) met rol-enum + unieke `(post_id, member_id)`;
  beide FK's `ON DELETE CASCADE`. Migratie `0033_event_attendance`.
- **AVG**: de expliciete wis-keten (`account_deletion`) verwijdert de aanmeldingen van een gewist lid; het
  event zelf blijft (community-waarde, `added_by` → NULL).
- **Service** `attendance_service`: `set_role` (upsert), `clear`, en `summaries`/`summary_for` die de stand van
  een hele lijst events in **één** query opbouwen (geen N+1) — tellingen + namen + de eigen keuze van de kijker.
- **Routes**: `POST /agenda/{id}/rsvp` (rol) + `POST /agenda/{id}/rsvp/clear`, login-gated (CSRF via body-
  `hx-headers`), htmx-swap van alléén de RSVP-strip. Ongeldige rol → 400; anon → /login.
- **Tests**: upsert (rol wijzigen = geen dubbele rij), summary-tellingen + namen + eigen keuze, route-swap met
  actieve staat, clear, anon-login-gate, ongeldige rol, account-deletion wist aanmeldingen. 1021 groen.
  Anon-strip + spreker-met-profiel-link visueel geverifieerd in de browser; de ingelogde klik-flow is via de
  end-to-end test gedekt (lokale HTTPS-cookie-constraint verhinderde de browser-klik).

## [0.83.0] - 2026-06-22
### Added — Agenda-categorieën (meetup/conferentie/coding/workshop/talk/hackathon/overig)
- Elk agenda-event heeft nu een **soort**: een korte, herkenbare set (geen vrije tags). Voedt een
  **categorie-badge** op de event-kaart (naast de kleur-gecodeerde frequentie-badge) én **filterchips** op
  `/agenda` — exact hetzelfde chip-patroon als de discipline-filter op `/leden` (deelbare, indexeerbare
  `?category=`-URL; htmx swapt alleen de lijst).
- **De AI vult 'm bij de draft**: `post_draft_service` extraheert de categorie in dezelfde, gegronde Haiku-
  tool-call (geen extra call). Onbekende/ontbrekende waarde → veilige default `meetup`.
- **Model**: nieuwe `EventCategory`-enum + nullable `Post.category` (VARCHAR + CHECK, dialect-neutraal).
  Additieve migratie `0032_event_category` (bestaande events houden geen soort → tonen geen badge).
- **Server-filter**: `post_service.list_events(category=…)` filtert op soort; een onbekende/lege waarde negeert
  de filter (alle events). `category_options()` voedt de chips + de form-select.
- **Tests**: draft mapt de categorie + valt terug bij een ongeldige waarde; submit-default = `meetup`; service-
  filter + chip-deeplink end-to-end. Volledige suite groen. Visueel geverifieerd in de browser (chiprij,
  badges, actieve chip-staat, deeplink-filter, event-zonder-soort toont geen badge).

## [0.82.0] - 2026-06-22
### Changed — Bijdragen via één slimme input (link/tekst/voice → de agent maakt de draft)
- De **ingewikkelde formulieren** op agenda én nieuws zijn weg als startpunt. Nu geef je **één ding** — een
  **link, wat tekst, of voice** — en de agent maakt er een concept van; jij controleert en plaatst. Dat is de
  stijl van het platform (verbazen door intelligentie, geen invulvelden).
- **Gegrond, nooit verzonnen**: `post_draft_service.draft_event`/`draft_news` doet één Haiku-tool-call; zit er
  een URL in, dan halen we eerst de échte pagina-inhoud op (Cloudflare markdown) en extraheren we UITSLUITEND
  wat daarin staat — geen gehallucineerde datum/locatie. Onbekende velden blijven leeg.
- **Fail-safe**: AI uit of een fout → een minimale draft (URL + titel uit de tekst) zodat het altijd werkt.
- De bestaande, werkende form blijft als **"concept — controleer & plaats"-stap** (pre-filled door de agent) →
  geen nieuw persist-pad, validatie ongemoeid. Na plaatsen wist de concept-zone + smart-input zichzelf.
- **Voice** = progressive enhancement (Web Speech API): de 🎤-knop verschijnt alleen waar de browser het kan,
  en dicteert in het veld. Nul serverkosten.
- **Tests**: draft-service (URL-extractie, fail-safe, AI-mapping, nooit-een-datum-verzinnen, ongeldige
  enum→default) + concept-routes (pre-filled form, login-gated). 1010 groen. Server-flow end-to-end
  geverifieerd met een ingelogde sessie (login→verify→smart-input→concept).

### Volgt nog (zelfde richting, eigen increment)
- Event-**categorieën** (meetup/conferentie/coding-sessie/…) + **RSVP** (aanwezig/organiserend/ik spreek hier).
- **AI-curatie** die de agenda zelf vult met échte NL/BE-events en auto-goedkeurt wat ze zeker weet (twijfel →
  admin-queue), in lijn met de gekozen bron-strategie.

## [0.81.0] - 2026-06-22
### Changed — Agenda & nieuws publiek leesbaar voor anonieme bezoekers
- Een anonieme bezoeker kan nu **`/agenda` en `/nieuws` direct lezen** (geen login-redirect meer) — passend
  bij het open platform; de open-preview-banner blijft staan. De pagina's zijn ook **indexeerbaar** (noindex
  weg) zodat de publieke community-content vindbaar wordt.
- **Schrijven blijft login-gated**: het toevoeg-formulier is voor anon vervangen door een lichte "Word lid"-
  uitnodiging; de POST-routes houden `require_member`. Pending/ongekeurd nieuws blijft nooit publiek zichtbaar.
- GET-routes gebruiken nu `current_member` (optioneel) i.p.v. `require_member`; admin-acties tonen alleen voor
  ingelogde admins.
- **UAT-contract bijgewerkt**: `/agenda` + `/nieuws` van `MEMBER_ONLY` → `PUBLIC_INDEXABLE` (de zelf-groeiende
  ervaring-UAT dwong dit netjes af). Tests: anon leest (200, geen noindex, geen formulier), anon POST → login,
  lid ziet het formulier. 999 groen.

## [0.80.1] - 2026-06-22
### Fixed — Ledengids 500 op Postgres: json-kolommen → jsonb (DISTINCT-operator)
- De `/leden`-query doet `SELECT DISTINCT` over hele Profile-rijen. Een gewone Postgres `json`-kolom heeft
  géén equality-operator → met de nieuwe `profile.open_to` (v0.80.0) crashte elke ledengids/-profielpagina
  met *"could not identify an equality operator for type json"* (Internal Server Error; in de browser gevangen).
- Fix: `open_to` én `offering.gallery_urls` zijn nu **jsonb** op Postgres (`app/models/types.py` `JSON_LIST` =
  `JSON().with_variant(JSONB, "postgresql")`; migratie 0031 ALTERt beide, no-op op SQLite). jsonb hééft equality.
- **Postgres-pariteit-test toegevoegd** die exact dit vangt (DISTINCT + open_to-filter op echte Postgres) —
  SQLite zag het niet (json==jsonb daar). `./scripts/test-postgres.sh` groen.

## [0.80.0] - 2026-06-22
### Added — "Waar ik voor opensta": engagement-beacons op elk profiel
- Elk profiel kan nu aangeven waar je voor benaderbaar bent: **klantwerk · trainingen · spreken ·
  interviews · samenwerkingen** (`Profile.open_to`, JSON; migratie 0030; catalogus in `openness_service`).
- **De amaze zit in de intelligentie + de ervaring:**
  - *Publieke beacons die iets dóen*: op je profiel worden de keuzes gloeiende signalen. Voor een bezoeker
    zijn ze **actionable** — één klik opent de concierge met een kant-en-klare intro ("Ik wil {naam}
    interviewen") via de bestaande `data-concierge-prefill`-haak (instant-laag = nul AI-kosten). Static label
    → directe interactie.
  - *Gegronde suggestie in de editor*: de agent stelt opties voor op basis van je werk-items (workshops →
    trainingen/spreken, publicaties → interviews, …) — `openness_service.infer_suggested`, zero-AI, jij kiest.
  - *Discoverability*: een "Open voor"-filterrij op `/leden` (zelfde chip-patroon als discipline) — vind wie
    openstaat voor spreken, interviews, samenwerking. Dialect-neutrale JSON-match (cast+LIKE op de catalogus-slug).
- Richards profiel staat op **interviews + samenwerkingen**.
- **Tests**: normalize/labels/intro/infer (catalogus), profiel-save (genormaliseerd, leeg → None), en de
  /leden open_to-filter. 995 groen. Migratie 0030 schoon (Postgres + SQLite).

### Fixed — Invite-mail & -landing pivot-conform
- De groep-invite-mail en de invite-landingpagina zeiden nog "besloten preview, alleen voor genodigden".
  Nu: het platform is **open**; de uitnodiging is een **directe sleutel** (wachtrij overslaan). Warme,
  persoonlijke toon behouden; alleen de gesloten-framing herschreven.

## [0.79.2] - 2026-06-22
### Fixed — Homepage-copy pivot-conform: van "besloten" naar "open"
- De hero-subkop én de SEO-omschrijving op de (nu publieke) homepage zeiden nog "Een besloten plek voor wie
  serieus met AI bouwt" — dat sprak de pivot (open, iedereen met AI-affiniteit) tegen, terwijl de preview-banner
  al "open" zei. Nu: "Een open plek voor iedereen in NL & BE die met AI bouwt, traint of er beleid over maakt."
- Sluit aan op de banner-wording en de pivot-beslissing; gewone, heldere taal (STYLEGUIDE). Alleen copy; de
  invite-only flow (invite-mail/landing) houdt bewust z'n eigen "besloten preview"-framing.

## [0.79.1] - 2026-06-22
### Changed — 🚀 Launch: de apex `dewereldvan.ai` serveert nu het platform (teaser eruit)
- **Apex-cut-over**: `dewereldvan.ai` + `www` wijzen niet langer naar de teaser-wachtlijst maar naar de
  volledige app. Mechaniek (Cloudflare API): de `dewereldvan-app`-tunnel kreeg apex+www als public-hostname
  (→ `web:8000`) vóór de DNS-flip (geen 404-venster), daarna de apex+www-CNAME's omgezet naar de app-tunnel.
- **Canonical naar de apex**: `BASE_URL`/`MCP_BASE_URL` op M4 → `https://dewereldvan.ai(/mcp/)`. `app.dewereldvan.ai`
  blijft óók de app serveren → bestaande magic-links en MCP-tokens breken niet.
- **Wachtlijst gemigreerd** (teaser-SQLite → `member`): 6 geldige adressen verzoend — 4 waren al approved lid,
  2 net-nieuw als `pending` (met `triage_note` "wachtlijst-import", `pending_expires_at=None` → blijven in de
  queue). Zo wordt het welkom heten via de bestaande approval→welkomstmail de menselijk-gecontroleerde
  launch-uitnodiging (geen massamail). De `.vom`-typo overgeslagen (correctie van dezelfde persoon bestond al).
- **Teaser buiten dienst**: stack gestopt (volume `waitlist-data` bewaard als backup, niet verwijderd).
- Geen code-wijziging (infra + data); browser-geverifieerd dat de apex het kosmische platform toont.

## [0.79.0] - 2026-06-22
### Added — Pivot Fase C (increment 4): galerij-werk-item — de pivot is compleet
- Designers, illustratoren en kunstenaars krijgen een native vorm: plak een portfolio-/galerij-link en de
  agent herkent dat het een **galerij** is → `kind=gallery` (render: eyebrow "Galerij", 🖼-kaartbadge,
  een **beeld-raster** als hero, "Bekijk het werk →"-CTA).
- **Nul-opslag, consistent met de oEmbed/unfurl-aanpak**: `project_enrich_service.extract_gallery_images`
  haalt de beeld-URLs uit dezelfde Cloudflare-markdown (geen extra fetch) en **hotlinkt** ze — de browser
  van de bezoeker laadt de beelden, niet onze server (geen SSRF, geen file-storage, geen op-last-verhoging).
  Filtert op absolute https + beeld-extensie, weert chrome (favicon/logo/sprite…), ontdubbelt, cap op 12.
- De classifier (`classify_work_item`) kreeg een categorie `gallery` erbij (één call, geen extra AI-kosten
  t.o.v. inc.3). **Fail-safe**: geclassificeerd als galerij maar < 2 bruikbare beelden → blijft project
  (nooit een lege galerij).
- **Datamodel**: additieve `offering.gallery_urls` (JSON, nullable; migratie 0029). Bestaande rijen ongemoeid.
- **Fase D uitgebreid**: nieuwe discipline **Design** (gallery) in de gids-filter + per-kaart-tag; de
  match-engine herkent een vraag om een portfolio/ontwerp/illustratie (`infer_desired_kinds`).
- **Tests**: `extract_gallery_images` (filter/dedup/cap/leeg), classifier→gallery, enrich-promotie naar
  gallery mét beelden + fallback-naar-project bij te weinig beeld. 987 groen. Browser-geverifieerd (grid +
  eyebrow + CTA renderen; geen JS-fout).
- **Opruiming**: wees-duplicaat `app/templates/projects/view 2.html` (per ongeluk meegecommit in v0.75.0,
  nergens gerenderd) verwijderd.

## [0.78.0] - 2026-06-22
### Added — Pivot fast-follow: discovery-op-discipline in de matchmaking
- De match-engine is nu **werk-soort-bewust**: vraagt iemands `Need` expliciet om een workshop, video,
  audio of publicatie ("ik zoek een workshop over RAG", "wie maakt video?"), dan komen werk-items van
  dát soort naar voren — óók als de woorden net niet overlappen. Zo gaat de net-geshipte discipline-data
  (Fase D) écht matchmaking voeden i.p.v. alleen de gids filteren.
- **Zero-AI, gegrond**: `members_service.infer_desired_kinds()` leidt de gewenste werk-soort(en) uit de
  vraag-tekst af (trefwoord/prefix-match op losse tokens; alleen hoog-signaal-soorten — `project` is de
  default, dus niet afgeleid). De kandidaat-ranking in `match_service` krijgt een `DISCIPLINE_BOOST`
  bovenop de bestaande tag- + woord-overlap-score, zodat passende werk-soorten in de kandidaatset belanden.
- Het **werk-soort** wordt nu ook meegegeven aan het LLM-oordeel (`[video-showreel]`/`[workshop/sessie]`
  …) en de matchmaker-instructie weegt het mee: een workshop past beter op een workshop-vraag dan een
  los project. Grounding ongewijzigd (alleen offering-ids uit de kandidaatset komen door).
- Geen datamodel-wijziging, geen migratie, geen extra AI-call, geen nieuwe op-last.
- **Tests**: `infer_desired_kinds` (NL/EN, meervoud, meerdere soorten, geen-match, project-uitsluiting) +
  een workshop-vraag die een workshop-werk-item in de kandidaten haalt ondanks nul woord-overlap. 981 groen.

## [0.77.1] - 2026-06-22
### Fixed — Discipline-chips: zuivere actief-staat + enkelvoud op de kaart
- De actieve filter-chip wordt nu puur door `:has(input:checked)` gestuurd (de `.is-active`-class werd stale na
  een htmx-grid-swap → kon twee chips highlighten). De server zet `checked` op de juiste radio voor deep-links.
- Per-maker discipline-tags zijn enkelvoud ("Bouwer"/"Trainer"/"Publicatie") i.p.v. de meervoud-filterlabels.

## [0.77.0] - 2026-06-22
### Added — Pivot Fase D: discipline-filter op de ledengids (de multidisciplinaire showcase wordt doorzoekbaar)
- De gids is nu te filteren op **discipline** (Bouwers · Video-AI · Audio-AI · Trainers · Publicaties) — een
  chiprij boven de constellatie. Zo vind je gericht "wie maakt video?", "welke trainers zijn er?", enz.
- **Geen apart datamodel**: een discipline ís de set werk-soorten die een maker toont — afgeleid uit de `kind`
  van z'n werk-items (`members_service`: `DISCIPLINES`-mapping → EXISTS-filter op `offering.kind`). De showcase
  classificeert de maker dus uit z'n eigen werk; nul migratie.
- De discipline-chips combineren met de bestaande tekstfilters (tag/maakt/zoekt/tool) in dezelfde htmx-submit
  (radio-chips, `:checked`-gestuurd, deep-linkbaar via `?discipline=`). Elke ledenkaart toont z'n discipline-tags.
- **Tests**: discipline-filter mapt op kind (video/bouwer), onbekend/leeg genegeerd; `derive_disciplines` in vaste
  volgorde; `discipline_options`-vorm. 979 groen.
- **Resterend van de pivot**: gallery (designers, multi-image) + discovery-verrijking op discipline (fast-follow).

## [0.76.0] - 2026-06-22
### Added — Pivot Fase C (increment 3): publicatie/artikel-werk-item + gegeneraliseerde classifier
- Onderzoekers en beleidsmakers krijgen een native vorm: plak een artikel-/publicatie-/paper-link en de agent
  herkent dat het een **publicatie** is → `kind=writing` (render: eyebrow "Publicatie", ✍-badge, "Lees het
  artikel →"-CTA, "Over deze publicatie").
- De workshop-detectie van inc.2 is **gegeneraliseerd** tot één Haiku-tool-call (`record_classification`,
  `classify_work_item`): één call classificeert de pagina als `event` → workshop (datum/locatie), `article` →
  writing, of `other` → blijft project. Geen extra AI-call t.o.v. inc.2; bij twijfel 'other' (fail-safe).
- Geen datamodel-wijziging (`writing` zat al in de `kind`-enum sinds inc.1). Render-only + service-refactor.
- **Tests**: classifier (event→workshop, article→writing, other→project, gated/geen-markdown) + enrich-promotie
  naar workshop én writing + gewoon-project blijft project. 976 groen.
- **Resterend**: gallery (designers, multi-image — eigen increment) + **Fase D** (discipline-facet + discovery).

## [0.75.1] - 2026-06-22
### Fixed — Geen lege cover-box + kind-bewuste sectiekop op de projectpagina
- Een werk-item zonder beeld én zonder embed (bv. een workshop in afwachting van de screenshot) toonde een
  lege, omrande cover-box. De hero rendert nu alleen nog bij een embed of een echt beeld. Browser-geverifieerd:
  de workshop-pagina opent direct op de titel + 🗓 datum · 📍 locatie-pills (geen leeg vak).
- De sectiekop "Over dit project" is kind-bewust: "Over deze workshop" bij een workshop.

## [0.75.0] - 2026-06-22
### Added — Pivot Fase C (increment 2): workshop/sessie-werk-item — datum + locatie uit een link
- Trainers krijgen een native vorm: plak een workshop-/event-link bij een werk-item en de agent herkent dat
  het een event is en haalt **datum + locatie** eruit (geen kaal formulier — verbaas-door-intelligentie).
- **`extract_event`** (`project_enrich_service`): een goedkope, gegronde **Haiku-tool-call** (`record_event`)
  op de al-opgehaalde pagina-markdown → `(event_at, location)` als het een event is, anders `None`. Gebruikt
  UITSLUITEND wat op de pagina staat (geen verzonnen datum/locatie). Loopt mee op de eerste verrijking (geen
  extra pagina-fetch), alleen voor `project`-items; fail-safe → blijft project.
- **`Offering`**: `event_at` (DateTime) + `location` (String) — migratie 0028 (additief, nullable). `kind` wordt
  `workshop` zodra een event herkend is.
- **Render**: de projectdetailpagina toont een workshop-meta-blok (🗓 datum · 📍 locatie, kosmische pills),
  kind-bewuste eyebrow "Workshop" + CTA "Naar de workshop →"; de profielkaart een 🗓-badge met datum.
- **Tests**: 9 nieuwe (`_parse_iso`-varianten; `extract_event` event/niet-event/gated/geen-markdown; `enrich_offering`
  promoot een event-link naar workshop, laat een gewoon project met rust). 974 groen.
- **Volgende increments** (zelfde model): gallery, writing; **Fase D** (discipline-facet + discovery).

## [0.74.1] - 2026-06-22
### Fixed — Schone console op de embed-speler
- De video-iframe had zowel `allow="fullscreen"` als het oudere `allowfullscreen` → browser-warning
  ("Allow attribute will take precedence"). De redundante `allowfullscreen` is weg; fullscreen blijft werken
  via `allow`. Live geverifieerd: de YouTube-showreel rendert in de kosmische 16:9-hero (eyebrow "Video").

## [0.74.0] - 2026-06-22
### Added — Pivot Fase C (increment 1): multidisciplinaire showcase — video/audio-showreel uit een link
- Het profiel toont werk nu in z'n eigen vorm. Eerste increment: **video- en audio-showreels** via oEmbed —
  een lid plakt een YouTube/Vimeo/SoundCloud/Spotify-link bij een werk-item en het wordt een ingesloten speler.
- **`Offering` gegeneraliseerd** (geen herbouw): `kind` (enum, default `project`; + video/audio/workshop/gallery/
  writing/link) + `embed_html`. Additieve migratie 0027 (`server_default='project'` → bestaande rijen ongemoeid).
- **`embed_service`**: detecteert de provider uit de host, haalt de oEmbed op en bouwt de `<iframe>` **zelf** uit
  een gevalideerde, https + allowlisted embed-src. **Geen SSRF** (we bevragen alleen onze bekende oEmbed-endpoints,
  nooit de lid-host), **geen XSS** (provider-HTML wordt niet vertrouwd; iframe sandboxed, lazy, geen autoplay).
  Fail-safe: geen match/fout/ongeldige src → link-fallback. Gratis → niet aan AI-gating gekoppeld.
- **Integratie**: `update_offering` resolvet de embed synchroon bij een URL-wijziging → `kind`=video/audio +
  `embed_html`, en slaat de screenshot-enrich over (een speler i.p.v. een screenshot). Rendering: de project-
  detailhero toont de speler (kind-bewuste eyebrow Video/Audio), de profielkaart een ▶/♪-badge.
- **Tests**: 17 nieuwe (`detect_kind`-matrix; `resolve` bouwt sandboxed iframe; weigert niet-allowlisted/non-https
  src; fail-safe op fout/ontbrekende iframe; `update_offering` zet kind+embed / valt terug op project). 965 groen.
- **Volgende increments** (zelfde model): workshop (datum + aanmeld/terugkijk), gallery, writing; discipline-facet (Fase D).

## [0.73.0] - 2026-06-22
### Changed — Admin-communicatie via Telegram i.p.v. e-mail (operator-voorkeur)
- Richard wil admin-features + -communicatie via z'n **Telegram-connectie**, niet z'n mail. Nieuwe
  `notification_service.notify_admins(db, notif)`: pusht een admin-seintje **direct** naar de geverifieerde
  Telegram van elke admin (op `admin_email_set`), ongeacht ieders persoonlijke voorkeurskanaal. Faalt nooit hard.
- **Nieuwe-aanmelding-notificatie** (`auth._notify_admins_new_registration`) gaat nu via Telegram i.p.v. een
  admin-e-mail (alleen bij een `review`-verdict; auto-welkom leden hoeven geen blik). De `EmailSender`-dependency
  is uit `register_submit` verwijderd (niet meer nodig). De queue blijft sowieso de bron van waarheid.
- **Nieuws-shortlist-notificatie** (`curate_news._notify_admins`) idem naar `notify_admins` (directe Telegram,
  niet meer afhankelijk van het persoonlijke voorkeurskanaal).
- **Recovery-route lekt je mail niet**: `support_contact` valt **niet** meer terug op het admin-adres — de
  "klopt er iets niet? mail ons"-regel verschijnt alleen als een los `CONTACT_EMAIL` is gezet (anders verborgen).
- **Vereist**: Richard moet z'n Telegram koppelen (`/profiel/notificaties`, @dewereldvanaibot) om de pushes te
  ontvangen; zonder koppeling no-op (queue blijft de bron). 2 nieuwe tests (admin-push alleen naar admin-Telegram;
  stil zonder koppeling). 948 groen.

## [0.72.0] - 2026-06-22
### Added — Pivot Fase B: AI-spam-triage + auto-welkom (de poort wordt slim) + open preview
- **De preview is open**: de banner zegt nu "Open preview — iedereen die met AI bouwt, leert of er beleid over
  maakt is welkom" (was "Besloten preview — alleen op uitnodiging"). We leven de pivot direct na.
- **Spam-triage bij registratie** (`triage_service.assess_registration`): een goedkope, snelle Claude-call
  (Haiku, `TRIAGE_MODEL`) beoordeelt **alleen** of een aanmelding van een echt mens lijkt of van een bot/spam —
  **nooit** of iemand "relevant/goed genoeg" is. Twee uitkomsten: `welcome` (lijkt echt) of `review` (twijfel).
- **Auto-welkom**: een `welcome`-verdict keurt het lid **direct** goed (krijgt meteen de welkomst-/login-mail);
  de aanmeld-pagina viert het ("Je bent erbij"). `review` blijft pending in de admin-queue, mét de triage-reden
  bij de kaart zodat je ziet wáárom een mens moet kijken. Jouw op-last daalt: alleen twijfel komt nog langs.
- **Nooit auto-weren**: er is geen auto-spam/auto-afwijzing — een AI-vergissing mag nooit een echt mens
  buitensluiten. Spam markeren blijft een handmatige actie. **KILL-fallback**: `AI_ENRICH_ENABLED` uit → alles
  `review` (= het gedrag van vóór de pivot); élke fout (geen key, netwerk, refusal, rare output) → `review`. De
  registratie strandt dus nooit op de AI.
- **Datamodel**: additieve migratie 0026 — `member.triage_note` (Text, nullable) voor de reden in de queue.
  Bestaande leden houden `NULL`. Config `triage_model` (default Haiku 4.5).
- **Tests**: 8 nieuwe (service: uit→review, WELKOM→welcome, BEKIJK/onverwacht/refusal/fout→review; route:
  auto-welkom keurt goed + viert, review blijft pending mét reden). conftest wist `ANTHROPIC_API_KEY` zodat de
  triage-call in de suite nooit écht belt (no-network-contract). 946 groen.

## [0.71.0] - 2026-06-22
### Added — Pivot Fase A: toegang herframen — de poort verwelkomt, oordeelt niet
- Eerste bouwfase van de open-showcase-pivot (`docs/PRD-open-showcase.md`): pure framing + genadige
  toestanden, **geen AI, geen datamodel-wijziging**. Lost direct de kernzorg op — niemand wordt als "niet
  geschikt" gekwalificeerd.
- **Registratie** (`/register`): open + multidisciplinair geframed ("voor iedereen die met AI bouwt, leert of
  er beleid over maakt — uit elke discipline"); de poort wordt uitgelegd als **anti-spam** ("we checken alleen
  even dat je geen bot bent"), niet als beoordeling.
- **Aanmelding-ontvangen** (`/register` → done): "Je bent aangemeld · we kijken alleen even mee dat je geen bot
  bent" i.p.v. "een beheerder beoordeelt je aanvraag". Welkomst-mail (`approval.html` + service-tekst) inclusief
  voor alle disciplines; subject "Je bent erbij — welkom".
- **Admin-queue**: heringericht als **spam-zeef, niet oordeel** — knoppen "Welkom heten" / "Markeer als spam"
  (was "Goedkeuren"/"Weigeren"), statuslabels nieuw/welkom/geschorst/spam, lede "de meeste mensen horen er gewoon
  bij; dit is alleen de spam-zeef".
- **Genadige herstel-route**: nieuwe `contact_email`-config (`support_contact` valt terug op het eerste
  admin-adres) → een neutrale "klopt er iets niet? mail ons"-regel op de aanmeld- en login-verstuurd-pagina’s,
  alleen getoond als een adres bekend is (geen kapotte link). Zet `CONTACT_EMAIL` op M4 om te overschrijven.
- **Tests**: register-framing (anti-spam + discipline), admin-queue-labels (welkom/spam, geen "weiger"),
  approval-mail-subject (welkom i.p.v. goedgekeurd). 938 groen.

## [0.70.2] - 2026-06-22
### Docs — Pivot vastgelegd: open multidisciplinair maker-platform met showcase (PRD APPROVAL PENDING)
- Strategische pivot van Richard: van besloten WhatsApp-groep → **open voor iedereen met AI-affiniteit, alle
  disciplines**, mét approval die **spam filtert i.p.v. mensen** (niemand wordt "niet geschikt" genoemd).
- Nieuwe PRD **`docs/PRD-open-showcase.md`** (v0.1.0, APPROVAL PENDING): drie lagen — toegang zonder oordeel
  (AI-spam-triage → auto-welkom + flag-review, genadige toestanden) · multidisciplinaire showcase (typed werk-
  item-model = generalisatie van `Offering` + agent-uit-link + oEmbed-embeds) · verbinding (matchmaking op de
  rijkere showcase). Fasering A→D, edge cases + succescriteria. **Geen code — wacht op akkoord.**
- Beslissing vastgelegd in `context/decisions.md` (2026-06-22, met de 3 bevestigde keuzes + afgewezen
  alternatieven). `docs/PRD.md` (v0.1.0 WhatsApp-MVP) gemarkeerd als gedeeltelijk gesuperseed. `status.md`
  bijgewerkt met de pivot als huidige focus.

## [0.70.1] - 2026-06-22
### Fixed — Voordeur-compositie: geen lege verticale ruimte meer onder de constellatie
- Op de publieke voordeur clusterden de (nu 3) makers in de bovenste 30% van een vaste `16/9`-constellatiebox
  (~517px hoog) → een gat van ~350px eronder vóór "Bekijk alle makers" en de community-kaarten. Browser-
  geverifieerd: de box is 518px→304px, de sterren spreiden nu over de volle box, het gat is weg.
- Twee gerichte ingrepen in de gedeelde `_constellation.html` + `cosmic.css`: (1) de coords zijn **progressief
  gebalanceerd** — elk prefix (de eerste N posities) spreidt al over breedte én hoogte; (2) een **count-bewuste**
  `home-constellation--sparse` (≤4 makers → kortere/smallere box: `5/2`, mobiel `1/1`). De volle `16/9` blijft voor
  ≥5 makers. Beide komen óók de lid-canvas-constellatie ten goede.
- **Tests**: route-asserties (`--sparse` bij 3 makers, niet bij 6) + de bestaande e2e-constellatie (5 makers,
  default box) bleef groen in echte Chromium. Live voordeur (3 echte makers) met eigen ogen geverifieerd.

## [0.70.0] - 2026-06-22
### Added — De lid-canvas wordt tijd-bewust: pas-verschenen makers gloeien (slice 2 van de verras-canvas)
- Slice 1 (v0.68.0) gaf de canvas-ruststaat de levende graaf; die was echter elk bezoek identiek. Nu is de
  constellatie **tijd-bewust**: makers die < 7 dagen geleden verschenen (zelfde `created_at`-bron als de
  nieuwe-makers-chip) schuiven naar voren in de zichtbare sterren én krijgen een zachte gouden "nieuw"-gloed +
  pill. De kop erkent de groei: "De wereld nu · {N} makers · {K} nieuw deze week ✦". Het lid ziet zo dat de
  wereld groeide terwijl het weg was — gegrond op echte data, **nul AI-kosten**.
- **AUGMENT, geen REPLACE**: de persoonlijke open-state-signalen (intro's/matches/discovery) worden al gedekt door
  de suggestie-chips onderaan de canvas (`nudge_service.select_chips`) — die heb ik bewust NIET gedupliceerd. Deze
  slice voegt een *visueel, in-graaf* groei-signaal toe dat de chips niet geven.
- Nieuwe helper `members_service.select_living_stars(profiles, *, now, limit, recent_days)` → `(stars, new_ids,
  new_count)`: puur in-memory op de al-geladen lijst (geen extra query; `member` is eager-geladen). `new_count`
  telt álle nieuwe makers (ook buiten de slice) voor de kop; `new_ids` alleen de zichtbare voor de gloed.
- `_constellation.html` kreeg een **opt-in** `new_star_ids`-flag → alleen de lid-canvas levert 'm; de publieke
  voordeur (`index.html`) blijft exact zoals 'ie was. CSS: `home-star--new` (ademende gloed, `prefers-reduced-
  motion` dooft de pulse) + de "nieuw"-pill, in `cosmic.css` (cache-bust via `asset_ver`).
- **Tests**: unit (`select_living_stars` — nieuw-eerst, ids, telling-voorbij-slice) + route (canvas gloeit/erkent
  bij recente makers; blijft rustig bij oude) + **e2e in echte Chromium** (glow + kop, geen JS-fouten). Visueel
  met eigen ogen geverifieerd op de ambient-screenshot. 940 unit + e2e groen.

## [0.69.0] - 2026-06-22
### Added — Goedgekeurde leden krijgen automatisch hun login-mail (geen handmatig porren meer)
- Tot nu toe stuurde "goedkeuren" in `/admin/queue` géén mail; Richard moest een goedgekeurd lid handmatig
  in de WhatsApp-groep porren om in te loggen. Nu stuurt `approve_member` (`app/services/approval.py`) zélf de
  welkomst-/login-mail (onderwerp "…je aanmelding is goedgekeurd", knop → `BASE_URL/login`), hergebruikt de
  bestaande kosmische `templates/emails/approval.html` (`render_approval`).
- **In de service, niet de route**: zo krijgt élk goedkeur-pad de mail automatisch mee (nu de admin-route, later
  een bulk-/auto-approve). Verzending via `get_email_sender()` — werkt met de Cloudflare-backend op M4 én de
  console-outbox in dev.
- **Fail-safe**: de mail-verzending zit in een try/except (`EmailSendError` + brede vangst) en mag de goedkeuring
  NOOIT breken — de status-transitie is al geflusht; bij een hapering loggen we en keren stil terug (lid kan altijd
  zelf via `/login` een verse magic-link halen).
- **Tests**: `test_approve_sends_login_email` (mail vertrekt met login-link) + `test_approve_survives_email_failure`
  (failure breekt de approval niet). Outbox-verificatie gedaan: de mail landt met `/login`-link in de console-outbox.

## [0.68.0] - 2026-06-21
### Changed — De lid-canvas landt niet meer leeg: ambient levende graaf (de regressie die Richard zag)
- Een ingelogd lid kreeg op `/` de agent-canvas met enkel een begroeting + leeg veld + 2 chips — "mooi maar
  leeg", verraste niemand (Richards observatie + "we moeten iedereen verrassen, zelfs mij"). De canvas toont nu
  in ruststaat de **echte levende makers-constellatie** ("De wereld nu · N makers") — dezelfde W1-graaf die de
  publieke voordeur al had, nu óók voor leden. Gegrond (echte leden + tag/tool-lijnen), **nul AI-kosten**.
  Verdwijnt zodra een gesprek begint (het antwoord krijgt focus).
- Constellatie geëxtraheerd naar herbruikbaar partial **`_constellation.html`** (voordeur + canvas delen 'm,
  geen duplicatie). Canvas-handler geeft `preview_stars`/`star_links`/`member_count` mee (zelfde poort-call).
- **Zelf in de browser geverifieerd, nu óók als ingelogd lid** (e2e `test_member_lands_in_canvas_agent_shell` +
  element-screenshot): de constellatie rendert echt in de canvas. 7 browser-tests groen, 930 unit groen.
- **Eerlijk**: dit is slice 1 (de levende graaf). Volgt: gegronde "sinds je weg was"-signalen (nieuwe makers,
  openstaande matches/intro's via `match_service`/`connections`) zodat de canvas nóg meer verrast.

## [0.67.0] - 2026-06-21
### Added — Browser-UAT (Laag 3) compleet + uitgevoerd: de échte ervaring in Chromium
- `tests/e2e/` (Playwright, `@pytest.mark.e2e`): start de **echte app** als uvicorn-subprocess tegen een geseede
  SQLite-DB (publieke makers + project), **AI uit** (nul kosten/netwerk), en drijft Chromium door de kern-
  journeys — wat TestClient per definitie niet kan (JS/htmx/SSE/canvas/motion).
- **6 tests, allemaal groen + visueel door mij geverifieerd** (screenshots bekeken): homepage W2-demo
  materialiseert écht (Lena Hart), W1-constellatie rendert 5 echte makers + verbindingslijnen, proef-chip opent
  de concierge voorgevuld, `/demo` speelt af mét causaliteit-regels (Nova Belmonte), `/leden` toont verbonden
  kaarten + graaf-graad, `/proef` rendert. **Harde JS-vangst**: elke pagina faalt bij een console-error/
  page-exception → gebroken JS wordt nu gevangen.
- `requirements-e2e.txt` (pytest-playwright/playwright) + nachtelijke/handmatige CI-job (`.github/workflows/e2e.yml`,
  installeert Chromium, draait `pytest -m e2e`). Screenshots gegitignored (regenereerbaar). Snelle suite blijft
  e2e uitsluiten (930 passed, 6 deselected).
- **Werkregel vastgelegd** (memory `feedback-verify-before-done`): nooit "af"/"werkt" claimen zonder het zelf
  gecontroleerd te hebben — voor UI in een echte browser.

## [0.66.1] - 2026-06-21
### Removed — Dode code opgeruimd (Tier 3 hygiëne)
- `app/templates/base.html` (het oude lichte thema — niemand extend't 'm, de "tweede-look-val" uit de audit),
  `app/templates/_flash.html` (alleen door base.html ge-include'd) en `app/static/app.css` (alleen door base.html
  gelinkt) verwijderd. Vooraf geverifieerd: geen enkele `{% extends %}`, include of render-call verwijst er
  functioneel naar (alleen comments/docstrings die "extendt base.html NIET" zeggen). Eén nu-misleidende
  cosmic.css-comment (verwees naar base.html-injectie) bijgewerkt. **930 tests groen, niets gebroken.**

## [0.66.0] - 2026-06-21
### Changed — Runtime Tailwind-CDN weg op alle publieke pagina's → statische util.css (FOUC weg)
- De render-blocking dev-CDN (`cdn.tailwindcss.com`) is op **alle 32 geserveerde cosmic-pagina's** vervangen door
  een handgeschreven statische **`app/static/util.css`** (cache-gebust) — geen FOUC/layout-shift meer op de
  mobiele WhatsApp-first-touch, en **géén build-pipeline** (CLAUDE.md: lage op-last). util.css bevat exact de
  utilities die de templates gebruiken (Tailwind-schaal), geverifieerd compleet: elke gebruikte utility-token op
  een geserveerde pagina heeft een regel (de "missende" licht-kleur-tokens zaten enkel in de dode `_flash.html`).
- **Regressie-guard** in de UAT (Laag 2): elke publieke cosmic-pagina mag de CDN NIET meer laden en moet util.css
  linken — nieuwe pagina's erven dit automatisch. **930 tests groen.**
- `base.html` + `_flash.html` blijven ongemoeid (dood: niemand extend't base.html) — losse hygiëne-opruiming later.

## [0.65.0] - 2026-06-21
### Added — Blok 3.6: agent-aan-de-deur op de invite-landing (Blok 3 compleet)
- De groep-invite-landing toont vóór het naam+e-mail-formulier nu de **gescripte agent-demo** (`_home_demo.html`
  + `demo-play.js`): de genodigde ziet meteen wat 'ie zo bouwt — geen kaal formulier meer. **Gescript = nul
  AI-kosten** (de echte AI-profielbouw gebeurt pas ná inloggen, leden-gecapt); het formulier zelf blijft exact
  ongemoeid (directe toegang, csrf-volgorde). +1 test. **930 tests groen.**
- Hiermee is **Blok 3** afgerond (project, nieuws, roadmap, agenda/concierge-contexts, ideeën, auth) en daarmee
  het volledige geprioriteerde ervaring-plan uit de audit (Blok 0 UAT → 1 homepage-kopstuk → 2 publieke pad →
  3 overige schermen). **Resterend buiten het plan**: volledige interactieve `/leden`-force-graph (L-effort) en
  de Tailwind dev-CDN → vooraf-gebouwde-CSS-migratie (FOUC, project-breed) — beide eigen blokken.

## [0.64.0] - 2026-06-21
### Added — Blok 3.5: ideeënbus krijgt een live 'lijkt-op'-hint (anti-duplicaat/anti-ruis)
- Tijdens het typen van een idee-titel toont een **live hint** (htmx, 400ms debounce) tot 3 bestaande ideeën die
  erop lijken, mét stemtelling, klikbaar naar het bestaande idee ("stem mee i.p.v. opnieuw indienen") — houdt de
  graaf schoon (anti-ruis = de noordster-toets voor dit scherm).
- **`idea_service.find_similar`**: Python-similariteit (difflib sequence-ratio + token-Jaccard, het maximum) →
  werkt identiek op SQLite én Postgres, deterministisch, **nul AI, geen pg_trgm-afhankelijkheid**. Korte titels
  (<4 tekens) geven niets (geen ruis bij de eerste letters).
- Nieuwe route `GET /ideeen/lijkt-op` (leden-only) — door de **zelf-groeiende UAT** automatisch afgedwongen te
  classificeren (de dekkingswacht deed precies z'n werk). +4 tests. **929 tests groen.**

## [0.63.1] - 2026-06-21
### Fixed — Blok 3.4: contextuele concierge-prompts (dode-haak-cluster, agenda + 5 anderen)
- 9 pagina's zetten `concierge_context`, maar alleen 3 (leden/roadmap/member) hadden een branch → agenda, home,
  nieuws, ideeën, project en profiel vielen door naar de generieke "Vraag de wereld iets…". Alle zes krijgen nu
  een eigen, simpele en directe prompt (agenda → "welke events passen bij mij?", home → "wie zit hier en wat
  maken ze?", project → "wie maakt dingen zoals dit?", enz.) — de concierge voelt overal contextbewust.
- +1 test (agenda) + bestaande placeholder-test herijkt op de nieuwe home-context. **922 tests groen.**

## [0.63.0] - 2026-06-21
### Added — Blok 3.3: roadmap toont gegronde idee-herkomst (levend + transparant)
- Een gepromoot roadmap-item toont nu **wélk lid-idee het voedt**: "✦ uit een idee van &lt;naam&gt; · N stemmen",
  klikbaar naar het idee (`/ideeen#idea-{id}`) — i.p.v. het generieke "uit de ideeenbus". Maakt zichtbaar dat
  de roadmap door de leden gevoed wordt (de transparantie-/levend-mandaat).
- `roadmap_service.list_grouped` eager-load't nu het gekoppelde idee + voorsteller + stemmen (`selectinload`/
  `joinedload`) → geen N+1. Bestaande `linked_idea`-relatie hergebruikt; **geen migratie, geen AI**. Verborgen
  ideeën tonen geen herkomst-link (valt terug op de neutrale tekst). +1 test. **921 tests groen.**

## [0.62.1] - 2026-06-21
### Changed — Blok 3.2: nieuws-graaf-verbinding leest als een edge (audit herijkt)
- De nieuws-kaart toonde de gegronde tool-match al (detectie-op-weergave; persistentie is bewust YAGNI, zie
  `post_service`/`_card.html`). De audit-suggestie "persist match + detecteer lid-namen" is daarom **niet**
  gevolgd: persistentie botst met die erfgoed-keuze, en lid-naam-detectie in vrije tekst riskeert false
  positives (ruis voor experts — KILL-risico uit de noordster).
- Wél: de bestaande `[data-connection]`-verbinding ("raakt &lt;tool&gt;") krijgt nu een eigen graaf-treatment
  (mono-cyaan label + zachte cyaan gloed op de chips) zodat 'm leest als een graaf-edge i.p.v. een gewone
  bronregel. CSS-only, geen migratie, geen false-positive-risico. **920 tests groen.**

## [0.62.0] - 2026-06-21
### Added — Blok 3.1: project-pagina maakt de (al gebouwde) intelligentie zichtbaar
- De AI-samenvatting wordt **gelabeld als agent-output + gegrond** ("✦ door de agent samengevat uit de live
  site") met materialize-reveal — de al-gebouwde enrich-intelligentie wordt nu zichtbaar i.p.v. anoniem.
- **Eerlijke "agent bekijkt dit project"-staat** wanneer enrich nog loopt (url aanwezig, nog geen samenvatting):
  een kosmisch reasoning-paneel i.p.v. een lege doos. Screenshot-hero krijgt `data-reveal="materialize"`.
- **Bug-fix**: de gouden "Bekijk →"-affordance op de maker-kaart was `.member-star__pull` zónder hover-trigger
  in een `.card` → permanent onzichtbaar; krijgt nu z'n eigen `.card:hover/:focus-within`-reveal.
- Geen backend-wijziging (de enrich-pipeline blijft zoals 'ie was). +2 tests. **920 tests groen.**

## [0.61.0] - 2026-06-21
### Added — Blok 2.4: /demo toont de scan→veld-causaliteit (Blok 2 compleet)
- Per materialiserend veld verschijnt nu synchroon een **reasoning-regel** ("homepage gelezen → naam + headline",
  "projecten gevonden: 2", "vraag/aanbod afgeleid", …) in het scan-paneel, zodat de bezoeker ZIET dat elk veld
  uit de scan kwam — geen blinde timer meer (W2-aanscherping). Gedreven door `data-demo-reason` op de stappen +
  een `[data-demo-reasons]`-uitvoer; de gedeelde `demo-play.js` emit ze synchroon met de materialisatie.
- **Reduced-motion** behoudt de causaliteit: alles direct zichtbaar mét de reason-regels (mechanisme blijft
  leesbaar, geen statische before/after). De homepage-mini-demo deelt het script maar heeft geen reasons → no-op.
- +1 test. **918 tests groen.** Hiermee is **Blok 2 (publieke pad)** afgerond: `/proef`, publiek profiel,
  `/leden`, `/demo`.

## [0.60.0] - 2026-06-21
### Added — Blok 2.3: /leden wordt een verbonden graaf + slimme filter
- **Verbindings-signaal per kaart** (`graph_service.connection_counts`, nieuw): elke maker toont z'n graaf-graad
  ("✦ verbonden met N makers", gegrond op gedeelde tags/tools, in-memory, nul AI) → de ledengids leest als een
  verbonden graaf i.p.v. losse kaarten, en blijft crawlbaar/responsive (tekst, geen fragiele canvas-graaf).
- **Slimme filter-autocomplete**: de Tag- en Tool-velden krijgen native `<datalist>`-suggesties uit de échte
  vocabulaire (`members_service.filter_vocabulary`) — alleen wat een bezoeker daadwerkelijk kan filteren.
- **Bug-fix**: een tool-only filter zonder resultaat toonde "Nog geen profielen" (helemaal-leeg) i.p.v. "Niets
  gevonden" (gefilterd-leeg) — `tool` ontbrak in de `_filtered`-check van `_grid.html`.
- +5 tests (graad-unit + bug-fix + signaal + autocomplete). **917 tests groen.**
- **Bewust uitgesteld**: een volledige interactieve force-graph met getekende edges (L-effort; vergt netwerk-
  dichtheid + a11y/SEO/mobiel-zorg). Het verbindings-signaal levert de graaf-lezing zonder die fragiliteit.

## [0.59.0] - 2026-06-21
### Added — Blok 2.2: publiek profiel wordt een graaf-knoop ("Verbonden in de wereld")
- **`graph_service.related_members`** (nieuw): tot 4 publieke makers die ≥1 tag of tool met een profiel delen,
  **strict uit de DB** (geen LLM, geen externe call → nul hallucinatie, nul kosten). Tools wegen zwaarder dan
  tags; in-memory over de publieke-profielen-poort (besloten/geschorst lekt nooit, geen N+1). Eén bron die
  **`/leden`** (Blok 2.4) straks hergebruikt — geen tweede implementatie.
- **Publiek profiel** (`profiles/view.html` + `view_profile`-handler): een "Verbonden in de wereld"-sectie met
  per buur een kaart (naam + headline + de **concrete gedeelde grond**, bv. "deelt tool: cursor" / "beiden in
  voice-agents") die naar `/leden/{slug}` linkt. Zet het meest-geïndexeerde scherm om van plat CV → knoop in de
  levende kaart, met interne linkwaarde voor SEO. Verschijnt alleen bij echte buren (anders weg, geen lege sectie).
- +6 tests (service-unit: paren/rangschikking/cap/privacy-uitsluiting + route). **913 tests groen.**

## [0.58.0] - 2026-06-21
### Added — Blok 2.1: /proef toont de agent áán het werk + gegrondheid (W4-richting)
- **Zichtbare "agent leest …"-staat** tijdens de (seconden-lange) call: i.p.v. een dode spinner verschijnt een
  kosmisch reasoning-paneel ("de agent leest <host> …" + scan-lijnen) via `hx-indicator`; de host wordt bij
  submit ingevuld. Het geld-kritische call-pad (`visitor_url_card.build_card` áchter `visitor_ai_guard`) is
  bewust **niet** aangeraakt — geen SSE-herbouw, geen extra spend-risico.
- **Bron-attributie** op de verse kaart ("✦ gelezen van <host>") — het anti-hallucinatie-/gegrondheids-signaal
  dat de noordster eist. Cache-hit-kaarten laten 'm weg (host onbekend).
- **Eerlijke lege-kaart-staat**: een refusal/te dunne pagina (lege kaarttekst) toont nu "we konden er weinig
  uit halen — probeer een rijkere pagina" i.p.v. een kale kaart met alleen een CTA.
- +3 tests (lees-staat, bron-attributie, lege-staat). **908 tests groen.**

## [0.57.1] - 2026-06-21
### Fixed — Budget-poort: anon-concierge triggert nooit meer de betaalde agent-stream (server-side)
- `/concierge/stream` short-circuit voor `member is None`: een anonieme bezoeker krijgt een "word lid"-
  uitnodiging i.p.v. een betaalde `stream_concierge`-call. Sluit de enige eerder-ongecapte betaalde
  niet-lid-route (de UI blokkeerde 'm al sinds v0.57.0; dit dekt ook directe/curl-aanroepen). Anon = ontdekken
  (gratis instant-matches + het gecapte `/proef`), lid = de agent — exact de noordster-grens. Beschermt de
  €50/wk-cap. De card-grounding/sessie-isolatie-test draait nu als lid; nieuwe test bewijst dat de betaalde
  call voor anon niet draait. **905 tests groen.**

## [0.57.0] - 2026-06-21
### Added — Homepage-kopstuk (Blok 1, Concept B-hybride): de voordeur BEWIJST de belofte i.p.v. te beweren
- **W2 — embedded agent-demo** (`_home_demo.html` + gedeelde `static/demo-play.js`): de agent bouwt vóór je
  ogen een (fictief, gelabeld) profiel uit één getypte link — char-voor-char typen → scan-regel → velden
  materialiseren één voor één. Speelt één keer af zodra het in beeld komt; reduced-motion toont alles direct;
  **no-JS/crawler-vangnet** in de `<noscript>`. `/demo` deelt nu dezelfde choreografie (inline-script weg → geen drift).
- **W1 — echte makers-constellatie** (`index.html` + `compute_graph_links` in `main.py`): tot 8 ECHTE publieke
  makers als sterren (naam + headline + avatar), met verbindingslijnen die **echt gedeelde grond** (tag/tool)
  tonen — strict in-memory, nul AI, nul extra query. Bij <3 makers een eerlijke tekst-fallback (nooit nep-sterren).
- **Proef-de-agent-chips** (`data-concierge-prefill` in `_concierge.html`): vullen het concierge-veld en tonen
  gratis client-side instant-matches uit de graaf. **Kosten-veiligheid**: voor een anonieme bezoeker is de
  betaalde agent-stream in de UI geblokkeerd (afsluit-rij → "word lid"; `htmx:confirm` cancelt elke submit) —
  noordster-grens: anon = ontdekken, lid = de agent.
- **Prominente `/proef`-CTA** (van begraven tekstlink → tweede knop), kosmische styling in `cosmic.css`
  (`.home-demo` / `.home-constellation` / `.home-star` / `.home-chip`), `preview_stars[:5]→[:8]`.
- Adversarieel geverifieerd (4 lenzen): no-JS-vangnet + anon-kosten-funnel gevangen en gefixt vóór commit.
  **+13 tests; 904 groen.**
- **Bekende follow-ups (geen blokker, geëscaleerd)**: (1) server-side budget-cap op anon-concierge
  (`/concierge/bericht`+`/stream` zijn nu ongecapt betaald voor anon — UI dicht, server volgt); (2) Tailwind
  dev-CDN op publieke pagina's vervangen door een vooraf-gebouwde CSS (FOUC-risico mobiel). Beide pre-existing.

## [0.56.0] - 2026-06-21
### Added — Slimme, zelf-groeiende UAT (Laag 1 + 2): "weet altijd zeker dat álles werkt, ook terwijl we doorbouwen"
- **Laag 1 — route-dekkingswacht** (`tests/test_uat_coverage.py`): enumereert via `app_get_routes` élke
  GET-route live en dwingt af: (a) **geen 5xx in geen enkele identiteit** (anon/lid/admin) — een 500 is hier
  een echte bug; (b) de **auth-poorten kloppen** (publiek→200, besloten→303 /login, admin→403 voor een gewoon
  lid); (c) een **volledigheids-gate** — élke route moet in precies één classificatie-bucket staan, dus een
  nieuwe pagina kan niet ongetest/ongeclassificeerd shippen (de zelf-groei).
- **Laag 2 — ervaring-invarianten** (`tests/test_uat_experience.py`): consolideert de verspreide per-pagina
  styleguide-asserties tot één afgedwongen contract op élke kosmische pagina — `class="cosmic"` + de drie
  verplichte fonts (Fraunces/JetBrains Mono/Spline Sans) + cache-gebust `cosmic.css` + géén sier-fonts; plus de
  vindbaarheidspoort (publiek-indexeerbaar = NIET noindex; besloten/auth = noindex). Een nieuwe publieke
  cosmic-pagina wordt automatisch in het contract afgedwongen.
- **Laag 3 — browser-journey-UAT** voorbereid: `e2e`-pytest-marker geregistreerd; de snelle suite (elke commit)
  sluit 'm uit (`addopts = -m 'not e2e'`), zodat de echte JS/htmx/SSE/canvas-journeys (W1-constellatie,
  `/demo`-materialisatie, magic-link-login, concierge-surface, `/proef`) nachtelijk/on-demand draaien met
  gestubde AI (nul kosten). Implementatie volgt ná het homepage-kopstuk (test de nieuwe ervaring direct).
- Helper `app_get_routes` toegevoegd aan `tests/_route_helpers.py`. **+188 UAT-checks; 891 tests groen.**

## [0.55.0] - 2026-06-21
### Added — Tool-reviews Fase C: mens-naast-AI-correctie (de experts maken de review beter)
- Een lid kan een AI-tool-review **aanvullen/corrigeren**; de aanvulling staat **náást** het AI-blok
  ("Aanvullingen uit het netwerk · Aangevuld door <lid>"), **nooit** stil over de AI heen — herkomst +
  attributie blijven zichtbaar (`docs/vision/03` §4.3). Zet het grootste geloofwaardigheidsrisico
  (experts die fouten zien) om in de sterkste feature.
- **`ToolReviewNote`** (migratie 0025): `tool_id`, `member_id` (SET NULL), `field` (welk onderdeel, nullable),
  `body`, `hidden`, `created_at`. Aparte tabel — raakt `tool.tool_review` nooit aan.
- **`tool_review_note_service`**: `add_note` (rate-limited per lid, `rate_limit_tool_note_per_hour=8`,
  body-cap), `list_notes` (alleen zichtbaar), `hide_note` (admin + AuditLog `tool_note_hidden`).
- **Routes** (`tools.py`): `POST /tools/{id}/correctie` (`require_member`), `POST /admin/tool-notes/{id}/verberg`
  (`require_admin`), `POST /tools/{id}/herzie` ("ververs nu", **bewust admin-only** voor AI-kostenbeheersing —
  leden beïnvloeden gratis via correcties + de nachtjob doet de cadans).
- **UI**: aanvullingen + correctie-formulier onder het dossier (`_tool_review_notes.html` /
  `_tool_review_note_form.html`), alleen voor ingelogde leden; admin krijgt verberg- + ververs-knoppen.
  Hergebruikt feedback/ideeën-styling, geen tweede look. 11 nieuwe tests. **703 tests groen.**

## [0.54.1] - 2026-06-21
### Fixed — tool-review-call gaf 400 (thinking + geforceerde tool_choice)
- Opus 4.8 weigert `thinking` zodra `tool_choice` tool-gebruik forceert ("Thinking may not be enabled when
  tool_choice forces tool use") → alle reviews vielen op `failed` (best-effort hield de oude review). `thinking`
  weggehaald uit de tool-review-call; de geforceerde `record_review` blijft (gegarandeerde structured output,
  extended thinking onnodig voor een gegronde extractie). Regressie-test borgt dat `thinking`/`temperature`/
  `budget_tokens` wegblijven. Gevonden door de eerste geobserveerde prod-run.

## [0.54.0] - 2026-06-21
### Added — AI-tool-reviews: de catalogus die zichzelf bijhoudt (Fase A+B)
- Claude reviewt automatisch de tools die leden gebruiken (`docs/vision/03`), getoond als **AI-dossier — geen
  sterren**. AUGMENT op het `project_enrich_service`-recept; operator-side (~€0,08/review, ~€4/kwartaal),
  raakt het €50-bezoekersbudget niet.
- **`Tool` augment** (migratie 0024): `tool_review` (JSON), `tool_reviewed_at`, `tool_review_status`
  (`ok`|`failed`|`no_source`). **`tool_review_service`** spiegelt `project_enrich`: `review`/`review_one`
  (eigen sessie, best-effort, nooit raisen) / `refresh_all` (idempotent) / `trigger_async` /
  `trigger_for_profile_tools` (warme trigger bij tool-koppelen).
- **Scope**: alleen tools met **≥1 lid-gebruiker** + valide `url` (geen url → `no_source`); re-review na 90d.
- **Eén gegronde call** (geen web_search/loop): `browser_render_service.markdown` (gecapt 12k) → Opus 4.8 met
  `record_review`-tool (geen `messages.parse`), strikte grounding + anti-marketing-prompt, `limitations`
  **verplicht niet-leeg**, `null` bij onbekend. **SSRF-guard** (`logo_service._safe_url`) vóór élke fetch.
  Refusal/parse-fail → `status='failed'` en de **oude review blijft staan** (nooit met leeg overschrijven).
- **UI**: kosmisch dossier (`_tool_review.html`) met AI-herkomst (`AI-REVIEW · host · datum`), labelblokken
  (Goed voor / Voor wie / Sterk / **Let op** / Prijsmodel / NL-BE), netwerk-strip "gebruikt door N leden",
  confidence-toon, AI-disclosure in gewone taal; goud micro-stipje + `<details>`-dossier op de tool-pill.
  Nachtjob `review_tools` (wekelijks/idempotent). 8 nieuwe tests. **691 tests groen.**

## [0.53.1] - 2026-06-21
### Fixed — `curate_news` crashte op echte tags (geobserveerde eerste run)
- `news_curation_service._group_context` las `t.name` op een `select(Tag.name)` (dat al strings oplevert) →
  `AttributeError` zodra er échte tags in de DB stonden. De unit-tests misten het (lege test-DB). Gefixt naar
  `t` (zoals de tools-regel ernaast al deed) + regressie-test met echte tag/tool-rijen. Gevonden door de
  eerste geobserveerde prod-run vóór de wekelijkse cadans aan ging — precies waarvoor die run bedoeld is.

## [0.53.0] - 2026-06-21
### Added — "De Briefing": AI-gecureerd wekelijks nieuws met mens-in-de-lus (MVP)
- Nieuws wordt geen aggregator-feed maar een **wekelijkse AI-gecureerde briefing** met duiding-per-item +
  verbanden naar leden/tools (`docs/vision/02`). **Operator-side** (~€0,10–0,45/wk) — raakt het €50-bezoekers-
  budget NIET; weergave kost €0 (alles vooraf gegenereerd).
- **`Post` augment** (migratie 0023, 5 nullable kolommen): `review_state` (live|pending_review|rejected,
  default live → lid-flow ongewijzigd), `source_kind` (member|ai_curated|member_media), `ai_relevance`,
  `ai_take` (de "waarom dit ertoe doet"-duiding), `briefing_week`. Geen tweede tabel (holistische `Post`-filosofie).
- **`news_curation_service`** spiegelt `footprint_service`: `web_search`+`web_fetch` op `claude-opus-4-8`,
  pause_turn-loop, `record_news_item`-tool (geen `messages.parse`), dedup-context (60d), groeps-context
  (tags + tool-catalogus), conservatieve **relevantie-drempel 70**. **`curate_news`-job** (best-effort,
  idempotent op url, gegated op `ai_enrich_enabled`), wekelijks in `nightly-jobs.sh` (zondag-gate).
- **Mens-in-de-lus is hard**: AI-kandidaten starten ALTIJD `pending_review`; `_visible` laat alleen `live`
  door (pending/rejected nooit publiek/geen unfurl); live worden kan enkel via `approve_news` op de admin-
  shortlist (`require_admin`, 1-klik goedkeuren/weigeren, htmx + AuditLog). In-app chip op het admin-dashboard.
- **UI**: "Deze week"-briefing-strip (constellatie-reveal + `ai_take`) bovenaan `/nieuws`, daaronder het
  archief; `_card.html` augment (herkomst-badge "gevonden door dewereldvan" + tool/lid-verbindingschip via
  detectie-op-weergave). Geen tweede look. 15 nieuwe tests. **682 tests groen.**

## [0.52.1] - 2026-06-21
### Fixed — htmx-geswapte resultaten bleven onzichtbaar (o.a. de /proef-mini-kaart)
- **Bug** (Richard: "de proef werkt niet"): de mini-kaart werd correct gegenereerd (call + boeking OK,
  goede inhoud) maar **verscheen niet**. De kaart draagt `data-reveal="materialize"` (start `opacity:0`)
  en werd via htmx in `#proef-resultaat` geswapt; de reveal-director onthulde geswapte content via de
  scroll-`IntersectionObserver` met `rootMargin: -8%` — een resultaat dat net onder de vouw / in die
  dode zone landt werd nooit "in beeld" gezien → bleef onzichtbaar tot je scrolde.
- **Fix** (`ai/_cosmic_canvas.html`): een htmx-swap is een **bewuste actie** (de gebruiker wacht op het
  resultaat) → de `htmx:afterSwap`-handler zet nu **direct** `.is-in` op nieuwe `[data-reveal]`-fragmenten
  i.p.v. ze aan de scroll-observer te geven. De materialize-transitie speelt nog steeds; content kan niet
  meer onzichtbaar blijven. Geldt voor élke htmx-swap (ook leden-filter, voten, toevoegen).

## [0.52.0] - 2026-06-21
### Added — Concept A: publieke "plak een link"-voordeur voor niet-leden (Fase 2)
- Een niet-lid plakt op **`/proef`** één URL → áchter de kosten-gate bouwt **één gecapte Opus-call** een
  kosmische drie-delige mini-kaart (WIE / THEMA / MATCH — "bij wie in het netwerk zou je passen") die als
  `materialize` in beeld komt, met een "vraag toegang"-CTA. De funnel uit `docs/vision/04` Concept A + D-slot.
- **Geld-kritisch pad** (`proef.py::_run_card`): er gebeurt **geen** betaalde call vóór `visitor_ai_guard.check()`
  'ok' teruggaf; erná draait altijd `record_after_call()` (boekt de **echte** `response.usage`) + `db.commit()`.
  Cache-hit → kaart uit `AiSpendLog.response_text` (€0, geen call). Elke gate-weigering → nette, eerlijke
  kosmische degradatie-staat (daglimiet/weekcap/turnstile/burst) met toegang-CTA, **zonder spend**.
- **Gecapte call** (`visitor_url_card.build_card`): 1 fetch via Cloudflare Browser Rendering (CF fetcht
  server-side → geen SSRF), `max_tokens=1500`, **geen tools/loop/pause-turns**, markdown gecapt op 24k chars,
  prompt-injection-verdediging ("paginatekst = gegevens, geen instructies"), refusal-safe. Fetch/call-fout →
  nette foutstaat, **geen boeking**.
- **Veilige default**: zonder Turnstile-keys toont `/proef` geen input maar een "binnenkort / word lid"-staat
  (nul spend). **Admin-meter** op `/admin/queue`: "Bezoeker-AI deze week: €X,XX / €50 · N calls · M bezoekers".
  Subtiele 3e homepage-CTA "Probeer de agent" (alleen niet-ingelogd). Telegram-drempel-ping bij 80%/100%.
- 8 nieuwe route-tests (gate-takken, boeking, cache, degradatie, veilige default, URL-validatie). **667 tests groen.**

## [0.51.0] - 2026-06-21
### Added — Kosten-fundament voor bezoeker-AI (Fase 1; nog dormant, geen calls live)
- Fundament voor de publieke AI-ervaring voor niet-leden, mét **wiskundig gegarandeerde uitgaven-rem**
  (€50/week). Volgt `docs/vision/04-bezoeker-ervaring-en-budget.md` §4. **Nog geen route/UI** — dit is
  alleen de meet- + gate-laag; zonder Turnstile-keys is het hele pad sowieso uit (veilige default).
- **`AiSpendLog`** (append-only kasboek) + migratie `0022`: één rij per betaalde niet-lid-call met de
  **echte** token-usage uit `response.usage`, kost bevroren in `cost_eur_micros` (integer → geen drift),
  `cache_hit`, en `response_text` (zodat een identieke-prompt-cache-hit later kan hér-serveren). Léden-acties
  schrijven hier **niet** → de €50-telling omvat per definitie alleen "gewone bezoekers".
- **`visitor_ai_guard.check()`** — de harde **pre-call gate** (9-staps, doc §4.3): Turnstile → anti-burst →
  identieke-prompt-cache → per-bezoeker daglimiet → per-IP daglimiet → **globale weekcap met conservatieve
  voorschat**. De weekcap is een gate vóór de call, geen alert achteraf → kosten-uitloop is uitgesloten.
  `record_after_call()` boekt de echte usage + signaleert een 80%/100%-drempelkruising (idempotent per week)
  voor een Telegram-ping.
- **`visitor_spend`** (metering: week-som over ISO-week, glijdende dag/IP-tellingen, cache-lookup, kost uit
  config-prijzen), **`turnstile_service`** (server-side siteverify; geen keys = pad uit), **`client_ip()`**
  (`CF-Connecting-IP`, faal-veilig — achter de Tunnel is `request.client.host` blind), en de **`dwv_vid`**
  signed-cookie visitor-id. Alle limieten zijn env-config (zonder deploy bij te stellen).
- 19 nieuwe tests (kostberekening, week-isolatie, daglimieten, weekcap, cache, Turnstile-default, anti-burst,
  drempelkruising, léden tellen niet mee). **659 tests groen.**

## [0.50.0] - 2026-06-21
### Changed — Motion-systeem volledig uitgerold over de showcase (synergie, één identiteit)
- Scroll-reveal + semantische varianten + per-bezoek-variatie (v0.49.0, bewezen op het profiel) nu op
  **alle showcase-/community-pagina's**: homepage, ledengids, projectpagina, agenda, nieuws, ideeënbus, roadmap.
  Elke pagina leeft nu terwijl je scrollt i.p.v. alles-in-één-klap; elke hero-titel **materializet** als
  signatuur; card-grids (homepage-"speelveld", leden-constellatie, profiel-projecten) komen met **drift**
  (wisselend links/rechts). Per load andere reveal-mood + constellatie-mood → herbezoek voelt nooit identiek.
- **Director htmx-bewust** (`ai/_cosmic_canvas.html`): geswapte `[data-reveal]`-fragmenten (filters, voten,
  toevoegen) worden her-geobserveerd zodat ze net zo netjes onthullen — geen onzichtbare geswapte content.
  Dit maakte het veilig om scroll-mode óók op de htmx-community-pagina's aan te zetten.
- Volledig reduced-motion-safe; geen tweede look (hergebruikt `cosmic.css`-vocabulaire). 641 tests groen.

## [0.49.1] - 2026-06-21
### Fixed — Cache-busting voor cosmic.css (scroll-reveal toonde niets door stale CDN-cache)
- **Bug** (live gevangen): Cloudflare cachet `cosmic.css` 4u (`cf-cache-status: HIT`). Na de v0.49.0-deploy
  serveerde de CDN de **oude** CSS zónder de `.is-in`-reveal-regel, terwijl de (dynamische) HTML al wél
  `data-reveal-scroll` + `.is-in` gebruikte. Gevolg: in scroll-mode kreeg de body geen `.ready` én pakte
  `.is-in` niet → **content bleef op `opacity:0`** (onzichtbaar) op de publieke profielpagina.
- **Cache-bust**: alle 31 `cosmic.css`-links krijgen `?v={{ asset_ver }}` (de mtime van het bestand, als
  Jinja-global in `main.py`). Een nieuwe deploy serveert automatisch een verse URL — geen CF-purge nodig,
  en dit voorkomt de hele klasse "stale CSS na deploy"-bugs voortaan.
- **JS-failsafe** (`ai/_cosmic_canvas.html`): mocht de `.is-in`-CSS ooit alsnog ontbreken, detecteert de
  director dat een onthuld element op `opacity:0` blijft en valt terug op `body.ready` — content kan dus
  **nooit** onzichtbaar blijven. Belt-and-suspenders bovenop de cache-bust.

## [0.49.0] - 2026-06-21
### Added — Ervaring: reveals verrassen elke keer opnieuw (geen herhaald trucje)
- **Waarom** (Richard, harde eis uit het Ervaringsmandaat): er was één uniforme entrance-reveal
  (22px omhoog + blur, identiek op élk scherm) en álles onthulde bij page-load — scrollen onthulde
  niets. Dat voelt als één herhaald trucje. De ervaring moet bezoekers **steeds opnieuw** verrassen.
- **Scroll-reveal** (`ai/_cosmic_canvas.html`): een reveal-director met `IntersectionObserver` onthult
  elementen pas als ze in beeld scrollen — de pagina blijft leven terwijl je leest. Opt-in per pagina
  via `data-reveal-scroll` op `<body>` (alleen read-only showcase; htmx-swap-pagina's houden het oude
  `body.ready`-pad, geen regressie). Zonder IO-support of bij reduced-motion → val terug op `body.ready`.
- **Semantische reveal-varianten** (`cosmic.css`, opt-in via `data-reveal="<naam>"`, hergebruikt de
  identiteit): `materialize` (hero/AI-inhoud vervaagt + schaalt in alsof de AI 'm net opbouwt) en
  `drift` (kaarten komen wisselend van links/rechts i.p.v. als één blok). Toegepast op de publieke
  profielpagina (`profiles/view.html`): identity = `materialize`, projectkaarten = `drift`.
- **Per-bezoek variatie** zodat een herbezoek nooit exact hetzelfde voelt: de director kiest per load
  één van 3 reveal-"moods" (subtiele easing-variatie) en de constellatie krijgt per load een andere
  mood (goud-dichtheid, drift-snelheid, link-bereik, lijn-warmte). Browser-`Math.random`, binnen één
  look. **Volledig reduced-motion-safe** (gedekt door het bestaande `[data-reveal]`-vangnet).
- Uitrol naar leden-grid / projecten / community volgt als fast-follow (v1 bewijst het op het profiel).

### Added — Zombie-vangnet voor discovery-runs (startup-sweep)
- **Probleem** (openstaande taak in `status.md`): een container-restart midden in een discovery-job liet
  de `discovery_run` op `running` staan zonder levende thread — een zombie die eeuwig "running" bleef.
  Dwong een handmatige check af vóór elke deploy.
- **`discovery_job_service.sweep_orphaned_runs(db)`**: markeert bij app-start elke `running`-run als
  `failed` (`error="onderbroken door herstart"` + `finished_at`). Idempotent; alleen `running` is
  verweesbaar (geen `queued`/`pending` in dit model — `start()` maakt de rij meteen `running`).
- **Ingehaakt in `_lifespan`** (`app/main.py`) vóór verkeer wordt geaccepteerd; best-effort try/except,
  zelfde patroon als de Telegram-registratie. DB is bij app-start al gemigreerd (Dockerfile-CMD).
- 4 nieuwe tests (`running`→`failed`, `done` blijft, schone staat → 0, idempotent).

- **637 → 641 tests groen.**

## [0.48.0] - 2026-06-21
### Added — "Bekijk als bezoeker": publieke preview vóór publicatie
- **Waarom** (Richard): je moet je eigen publieke profiel heel makkelijk kunnen bekijken zoals
  anderen het zien, **vóór** je het publiceert — zonder eerst openbaar te moeten zetten.
- **Route** `GET /profiel/voorbeeld` (owner-only, `require_member`): rendert dezelfde
  `profiles/view.html` als de publieke pagina maar met `is_owner=False` (de bezoekers-ervaring,
  niet de eigenaar-nav) en `preview=True`. Werkt óók als het profiel nog `members`-only is —
  `can_view` wordt bewust omzeild (het is de eigen route van de eigenaar).
- **Altijd veilig voor SEO**: de preview is altijd `noindex` en emit nooit OG/JSON-LD, ongeacht de
  live-zichtbaarheid (geen lek in zoekmachines of link-unfurls).
- **Preview-chrome** (`profiles/_preview_frame.html` + `.preview-frame` in `cosmic.css`): een rustige,
  sticky kosmische bovenbalk die de pagina omkadert. **Progress-bewust**: bij `members`-only toont 'ie
  "Nog niet openbaar" + actie "Maak openbaar →"; bij `public` "Openbaar" + "Zichtbaarheid" (geen dode
  knop). Plain microcopy (styleguide §3), hergebruikt bestaande tokens — geen tweede look.
- **Ingangen** ("heel makkelijk"): bewerk-pagina-header ("Bekijk als bezoeker →"), de zichtbaarheid-sectie
  (deep-link `#zichtbaarheid`) en de AI-publiceer-dok (opent in nieuw tabblad zodat de live-bouw niet
  verloren gaat).
- 4 nieuwe route-tests (guard anon/pending → /login; members-only toont bezoekers-view + chrome + noindex;
  public toont openbaar-staat). **637 tests groen**.

### Removed
- 4 verouderde iCloud-conflictkopieën (`… 2.py`/`… 2.html`) opgeruimd; de originelen superseden ze.

## [0.47.0] - 2026-06-20
### Changed — Discovery is nu progress-bewust (geen "verse" affordance die al gebruikt is)
- **Probleem** (Richard): na een ontdekking bleef de CTA "Zal ik je online opzoeken?" staan alsof het vers
  was, en het media-aanbod bleef "zoek media" tonen ook nadat de media-pass al gelopen had. De interface moet
  begrijpen wat al gebruikt is en de vervolgstap aanpassen.
- **Stateful**: `DiscoveryRun.passes` (migr. 0021) onthoudt welke focus-passes voltooid zijn (`["broad","media"]`).
  Elke voltooide pass voegt zich toe; een verse brede zoektocht reset 'm.
- **Aangepaste affordances**:
  - Bouw-pagina-CTA: nog niet opgezocht → "Zal ik je online opzoeken?"; al wél → "Bekijk je ontdekking"
    (+ hint dat je nu media kunt laten zoeken als die pass nog niet liep).
  - Verdiepings-aanbod: zolang media niet liep → "Kom je weleens in het nieuws? → Ja, zoek media"; daarna →
    "Ik heb ook naar media gezocht" (geen dode knop). Geldt op de resultaat-view én na een live-pass.
- 6 nieuwe tests (passes per focus, reset bij verse zoektocht, offer toont/verbergt). **633 tests groen**.

## [0.46.0] - 2026-06-20
### Added — Discovery-verdieping: gerichte media-pass (opt-in)
- Na de brede ontdekking (eigen werk) biedt de agent een **verdieping** aan: *"Kom je weleens in het nieuws of
  media? Dan zoek ik ook naar interviews, artikelen en vermeldingen óver jou."* → [Ja, zoek media] / [nee].
- **Focus-parameter op de engine**: `footprint_service.discover(..., focus="media")` richt de zoek-intent op
  media WAARIN het lid genoemd/geïnterviewd wordt (niet eigen projecten), classificeert als media/talk, met
  dezelfde anker-disambiguatie.
- **Append-model** (geen schema-wijziging): de media-pass draait als dezelfde achtergrond-job en **vult de
  bestaande `DiscoveryRun` aan**, gededupeerd op URL (projecten blijven, media erbij); `seen_at` reset zodat het
  klaar-seintje opnieuw afgaat (push meldt alleen de NIEUW gevonden media). Crystalliseren → nieuws-`Post`
  (al ondersteund). Het aanbod staat op de resultaat-view én na een gelukte live-pass.
- **Events** als eigen focus uitgesteld (fast-follow; de focus-parameter generaliseert). PRD:
  `docs/PRD-discovery-verdieping.md`. 8 nieuwe tests. **629 tests groen**, ruff clean.

## [0.45.0] - 2026-06-20
### Fixed — Telegram koppelen is nu opt-in (voorkeur auto op telegram)
- **Probleem**: een lid dat Telegram koppelde kreeg tóch geen push — het voorkeurskanaal bleef op de default
  `in_app` (koppelen en voorkeur-kiezen waren twee losse stappen). Wie de moeite neemt te verbinden, wil daar
  z'n seintjes.
- **Fix**: `link_telegram_from_start` zet bij een succesvolle koppeling het `notification_pref` meteen op
  `telegram` (omkeerbaar in het paneel). 2 tests toegevoegd/aangescherpt (webhook + service). 623 tests groen.

## [0.44.2] - 2026-06-20
### Changed — source-of-truth-opschoning (audit-fix)
- Audit wees uit dat de canonieke context-docs ~29 versies waren weggedreven (en de richting tégenspraken,
  bv. e-mail-taken die we kilden). Hersteld:
  - **`context/status.md`** herschreven als levende single source of truth: huidige versie, wat er live staat,
    échte focus + open taken, en een pointer-map naar CHANGELOG/PRD's/decisions/memory.
  - **`context/decisions.md`** bijgewerkt met de 5 onvastgelegde keuzes (Discovery-fasering + auto-≥90,
    achtergrond-job, geen-e-mail/lid-gekozen-kanaal, Telegram-webhook).
  - **`context/architecture.md`** herschreven als canonieke systeemkaart: route-inventaris, datamodel
    (25 tabellen ↔ migraties 0001–0020), env-vars, fase-status.
  - **Discipline** vastgelegd in project-`CLAUDE.md`: status + decisions updaten bij elke VERSION/CHANGELOG-bump.
- **Repo-hygiëne**: 3 stray git-tracked duplicaten verwijderd (`app/services/ai_profile 2.py`,
  `app/templates/demo 2.html`, `docs/PRD-verificatie-links 2.md`) — nergens geïmporteerd. 622 tests groen.

## [0.44.1] - 2026-06-20
### Fixed — leeg scherm op /profiel/notificaties (en /…/ontdek/resultaat)
- De standalone kosmische pagina's includeden `ai/_cosmic_canvas.html` niet → `.ready` werd nooit op `<body>`
  gezet, dus alle `[data-reveal]`-inhoud bleef op `opacity:0` (leeg scherm). Beide pagina's includen nu de
  entrance-gate. Regressie-borg in de tests (de pagina bevat `classList.add('ready')`). 622 tests groen.

## [0.44.0] - 2026-06-20
### Fixed — de concierge vindt nu je notificatie-instellingen ("telegram" → instellingen, niet maker-zoek)
- **Probleem**: een lid dat z'n instellingen niet vond, vroeg de concierge "telegram" — die zocht er een
  *maker* bij ("geen makers met telegram gevonden") i.p.v. naar de notificatie-instellingen te leiden. Tegen
  het "agent-is-de-shell"-mandaat: de concierge is de navigatie, dus die moet z'n eigen instellingen kennen.
- **Notificaties als in-canvas surface** (zoals `verbind`): nieuwe `notificaties`-surface materialiseert het
  kanaal/Telegram-paneel ín de canvas (geen paginawissel). Bedraad op drie lagen:
  1. **Instant-laag** (⌘K): nieuwe route "Notificaties" met trefwoorden incl. *telegram, seintje, meldingen,
     instellingen* → directe hit zonder LLM (alleen voor ingelogde leden).
  2. **Concierge-engine**: `notificaties` in `SURFACE_REGISTRY` + route-tabel; systeem-prompt leidt
     *telegram/seintjes/meldingen/instellingen* expliciet naar `surface notificaties` — en stuurt "telegram"
     NOOIT meer naar `search_members`.
  3. **Router**: `_load_notifications`-loader + `/profiel/notificaties` → in-canvas surface-mapping.
- 6 nieuwe tests (surface overleeft de grounding-poort, loader rendert het paneel, instant-index toont/verbergt
  de route). **622 tests groen**.

## [0.43.0] - 2026-06-20
### Added — Bot-avatar + rich Telegram-content
- **Eigen kosmische avatar** voor @dewereldvanaibot: een on-brand beeld (deep-indigo + nebula-gloed + de gouden
  ✦ key-star, eigen achtergrond) gegenereerd en via **`setMyProfilePhoto`** (Bot API 9.4, feb 2026) live op de
  bot gezet. Asset: `app/static/telegram-avatar.jpeg`. Bot heeft ook een omschrijving + `/start`-commando.
- **Rich content versturen**: `telegram_service.send_message` ondersteunt nu `parse_mode=HTML` (vette titel) +
  een **tikbare inline-knop** (`button_text`/`button_url`) i.p.v. een kale URL. `notify()` stuurt voortaan een
  rich bericht: vette titel, body (HTML-escaped tegen injectie) en een knop naar de actie ("Bekijk je
  ontdekking" → de resultaatpagina; "Bekijk de intro"). De koppel-bevestiging in de bot is ook rich.
- Onderbouwd op de Telegram Bot API-releases van 2026 (9.4 profielfoto-beheer; 10.1 rich messages). We
  gebruiken de robuuste HTML + inline-keyboard-route (breed ondersteund).
- 3 tests bijgewerkt/toegevoegd (rich tekst + knop-args, HTML-escaping van user-content). **618 tests groen**,
  ruff clean op de nieuwe bestanden.

## [0.42.0] - 2026-06-20
### Added — Lid-gekozen notificatiekanaal (Telegram) + e-mail eruit (behalve magic-link)
- **Richting** (Richard): e-mail is verouderd → we sturen geen e-mail meer behalve de magic-link. Alle overige
  seintjes gaan naar een **door het lid gekozen kanaal**. Zie `docs/PRD-notificaties.md` + memory.
- **Uitbreidbare notificatie-laag** (AUGMENT, geen tweede systeem): in-app blijft de bestaande state-derived
  pull-chips; een nieuwe `notify(member, event)`-dispatcher voegt een **push** toe naar het voorkeurskanaal.
  Nieuw kanaal = een Notifier erbij. Modellen `member_channel` (gekoppeld adres per kanaal) + `notification_pref`
  (gekozen kanaal, default `in_app`) — migratie 0020, CASCADE + AVG-wis.
- **Telegram** (gegate op `TELEGRAM_BOT_TOKEN`): koppelen via deep-link `t.me/<bot>?start=<token>` + **webhook**
  (`POST /telegram/webhook`, secret-header-validatie, CSRF-exempt), idempotente `setWebhook` bij startup.
  Verzenden via de Bot API. Instellingen-pagina **`/profiel/notificaties`** (kanaalkeuze + koppelen/ontkoppelen).
- **E-mail eruit**: de discovery-klaar- én de matchmaking-intro-mails lopen nu via `notify()` (in-app pull +
  optioneel Telegram-push). Magic-link blijft de enige e-mail. Trade-off: een lid met default in-app dat de app
  niet opent mist realtime — Telegram is dé manier voor push (bewuste keuze).
- 15 nieuwe tests (parse_start, voorkeur + koppel-flow + dispatch-gating, webhook secret/koppelen,
  instellingen-route) + `member_channel`/`notification_pref` in de account-wis-compleetheidstest; intro-test
  van e-mail → notify. Migratie 0020 up/down bewezen. **617 tests groen**, ruff clean op de nieuwe bestanden.
- **Setup (Richard, eenmalig)**: bot via @BotFather → zet `TELEGRAM_BOT_TOKEN` + `TELEGRAM_BOT_USERNAME` +
  `TELEGRAM_WEBHOOK_SECRET` in de M4-`.env` → redeploy (webhook registreert zichzelf).

## [0.41.0] - 2026-06-20
### Changed — Discovery-seintje weg van e-mail + directe deeplink naar je resultaat
- **Geen e-mail meer voor de ontdekking** (e-mail blijft alléén voor de magic-link). Richting: e-mail is een
  verouderd concept; notificaties horen waar de aandacht al is. De discovery-job stuurt nu **geen mail** — het
  seintje is de pull-based **in-app chip** ("Je ontdekking is klaar"). Sluit aan op de Scout-PRD-pivot
  ("pull-only, geen e-mail, geen push").
- **Chip → directe deeplink**: de "klaar"-chip linkt nu naar een nieuwe pagina **`GET /profiel/ai/ontdek/resultaat`**
  die meteen je bewaarde resultaat toont (en `seen_at` zet → chip verdwijnt). Nog lopend / niets / mislukt →
  terug naar de bouwpagina. Standalone kosmische pagina (`discovery/resultaat.html`), hergebruikt de 1b-kaarten
  in review-modus.
- **Copy gelijkgetrokken**: het werkveld, de bouw-CTA en de tail-time-out zeggen nu "ik geef je een seintje in
  de app" i.p.v. "ik mail je".
- Voorbereiding op een **lid-gekozen notificatiekanaal** (Telegram + uitbreidbaar) — aparte voorkeurslaag,
  volgt in een eigen PRD.
- Tests bijgewerkt (geen-e-mail in de job, deeplink-pagina toont/markeert/redirect, chip linkt naar de deeplink).
  **602 tests groen**, ruff clean op de gewijzigde bestanden.

## [0.40.0] - 2026-06-20
### Changed — Discovery draait nu als achtergrond-job (weglopen → seintje → terugkeren)
- **Probleem**: het speurwerk duurt vaak >5 min, maar de live-SSE-stream sneuvelde al na **2 min**
  (`CHANNEL_TIMEOUT_SEC`) — de ontdekking bereikte het einde nooit, en niets werd bewaard, dus terugkeren
  naar het resultaat kon niet.
- **Oplossing**: de ontdekking is **ontkoppeld van het browservenster**. Een achtergrond-thread
  (`discovery_job_service`, eigen sessie zoals de project-enrich) draait de engine en **persisteert** de
  bevindingen naar een nieuw `DiscoveryRun`-model (migratie 0019, één run per lid, CASCADE + AVG-wis). De
  live-view **tailt** die run over SSE; `Last-Event-ID` laat 'm na een reconnect hervatten zonder kaarten te
  herhalen. De 2-min-cap raakt de job niet meer.
- **Je mag wegklikken**: het werkveld zegt nu eerlijk *"Dit duurt een paar minuten — kijk gerust rond, ik mail
  je zodra het klaar is en bewaar het resultaat."* De job loopt door als je weggaat.
- **Seintje bij klaar (beide kanalen)**: een **in-app chip** ("Je ontdekking is klaar — N vermeldingen",
  hoogste prioriteit in de canvas-nudge-laag) **én** een **e-mail** met een link terug. De e-mail is de fix
  voor wie de site verliet.
- **Terugkeren**: open de ontdek-actie opnieuw → je ziet meteen het **bewaarde resultaat** (en het markeert
  zich als gezien, chip verdwijnt). "Opnieuw zoeken" (`force`) herstart de job. Op terugkeer koppelt niets
  automatisch (review-modus); crystalliseren is bovendien **idempotent op URL** → geen duplicaten bij
  her-render/dubbelklik/reload.
- 12 nieuwe tests (job persist/empty/notify, tail + Last-Event-ID-hervatting, resume/running/force,
  klaar-chip aan/uit, URL-idempotentie) + DiscoveryRun in de account-wis-compleetheidstest. Migratie 0019
  up/down bewezen op SQLite. **598 tests groen**, ruff clean op de gewijzigde bestanden.

## [0.39.0] - 2026-06-20
### Added — Discovery (Fase 1b): de crystalliseer/bevestig-laag
- **Een vondst wordt nu écht je profiel.** Waar 1a kandidaten liet voorbijvliegen, koppelt 1b ze: een vondst
  met **hoge zekerheid** (`footprint_service.HIGH_CONFIDENCE` = 90) **crystalliseert live** — de kaart koppelt
  zichzelf na de fly-in (htmx `load`-trigger) mét een korte settle-glow en een makkelijke **"Ongedaan maken"**.
  Een **twijfelgeval** gaat naar de 1-klik **"klopt dit?"-bevestigrij** (✓ Koppelen / Aanpassen / ✗ Negeren).
  Conservatief hoge drempel zodat een false-positive — dodelijk voor dit expert-publiek — nooit ongevraagd landt.
- **Crystalliseren maakt echte graaf-entiteiten** via de bestaande paden (geen duplicatie): project → `Offering`
  (+ automatische screenshot/samenvatting-enrich via `trigger_async`); media/blog/talk/social/overig → nieuws-
  `Post` met de passende **rol-badge** (blog = geschreven, talk/media = vermeld, rest = gedeeld). De
  crystalliseer-stap leeft in `footprint_service` zodat de **Scout (Fase 2)** 'm hergebruikt.
- **Self-only + reversibel**: nieuwe routes `POST /profiel/ai/ontdek/crystalliseer` (koppelt, geeft de undo-kaart)
  en `POST /profiel/ai/ontdek/ongedaan` (verwijdert de entiteit, eigendom afgedwongen: Offering↔profiel,
  Post↔`added_by_id`) + her-koppel-affordance. CSRF via de hx-headers op `<body>`; grounding-poort
  (leeg/onveilig URL → geen koppeling). prefers-reduced-motion-veilig.
- 15 nieuwe tests (crystalliseer project→Offering & media→nieuws + rol-mapping, undo + ownership-poort,
  threshold, auto-vs-bevestigrij-markup, enrich-trigger alleen bij project). **586 tests groen**, ruff clean.
  PRD: `docs/PRD-discovery.md` (Fase 1). Volgt: in-canvas concierge-integratie + de Scout (Fase 2).

## [0.38.1] - 2026-06-20
### Changed — werkveld zet nu de tijdsverwachting eerlijk
- Het werkveld toont een **persistente verwachtings-regel** (roteert niet: "Goed speurwerk kost even — ik zoek
  het web echt af … meestal een halve tot een hele minuut") + een **subtiele live seconden-teller** (eerlijk
  "het loopt", geen nep-balk). De Discovery-CTA-copy benoemt de duur ook vooraf. Zo weet een lid dat de AI hier
  echt tijd voor nodig heeft i.p.v. te denken dat het hangt.

## [0.38.0] - 2026-06-20
### Added — een levend "de agent is bezig"-werkveld (herbruikbaar) + echte voortgang in Discovery
- **Probleem**: bij trage AI-acties (Discovery web-search ~20-40s) zag je alleen een statisch tekstje en leek
  er niets te gebeuren. Nu een herbruikbaar **cosmic working-state** component (`_cosmic_working.html` +
  `.cosmic-working` in cosmic.css): een constellatie-denkveld dat continu beweegt (orbiterende lichtpunten +
  pulserende kern + ademende nevel), met een statusregel die de **echte fases narreert** en — bij stilte —
  on-brand geruststellingen roteert zodat het nooit bevriest. prefers-reduced-motion-veilig, aria-live, weinig
  DOM-nodes (alleen transform/opacity).
- **Waarheidsgetrouw**: `footprint_service` emit nu tijdens de stream echte `fetch`-fase-events ("Ik doorzoek
  het web…", "Ik lees de bronnen en weeg wat écht van jou is…"); de statusregel swapt daarop declaratief
  (htmx-ext-sse), een MutationObserver laat een echt event altijd de idle-rotatie overrulen. Geen
  nep-voortgangsbalk.
- **Herbruikbaar**: drop-in in elke SSE-host; klaar voor de concierge-stream en profielbouw. 571 tests groen.

## [0.37.0] - 2026-06-20
### Added — Discovery (Fase 1a): live ontdekking van je online voetafdruk
- **Vraag de AI om je op te zoeken** → de footprint-engine doet een slimme web-search, beslist per resultaat
  of het ÉCHT jij bent (entity-resolution met de eigen links als anker, om naamgenoten uit te sluiten),
  classificeert (project / media / blog / talk / social / overig) met een confidence + "waarom dit jij is",
  en laat de kandidaten **live in de canvas voorbijvliegen + crystalliseren** (SSE, kosmische animatie).
- **`footprint_service`**: één Claude-call met de web_search/web_fetch server-tools + een `record_findings`-tool
  (pause_turn-veilig, geen `.parse()`, Opus-contract). Strikte grounding: findings zonder echte http(s)-URL
  vallen weg, confidence geklemd 0-100, type naar de enum, javascript:-URLs gedropt. Gegated op
  `AI_ENRICH_ENABLED`, best-effort (nette `done` op elke faaltak).
- **Self-only + consent**: alleen je eigen profiel (`require_member`), CSRF op de POSTs, en NIETS wordt
  opgeslagen zonder jouw **"Klopt dit? ✓ Koppelen"**-klik → een voorgevuld draft naar de bestaande endpoints
  (project → `/profiel/ai/offering` → pikt automatisch de screenshot+samenvatting op; media/blog → `/nieuws`
  met rol-badge). Geen persoonsfoto-scraping (Fase 3). Geen eigen fetch-surface (geen SSRF).
- Gebouwd + adversarieel gereviewd (XSS/grounding/AVG/SSE-loop/SSRF → PASS, geen blockers). 571 tests groen.
  PRD: `docs/PRD-discovery.md`. Volgt: in-canvas concierge-integratie + de Scout die de engine continu draait.

## [0.36.0] - 2026-06-20
### Added — AI-toolsets op profielen (selecteer leden op tool/toolset)
- **Leden voegen de AI-tools toe die ze gebruiken** (Claude Code, Cursor, Perplexity, Obsidian, …), mét logo +
  link. Gestructureerde **`Tool`-catalogus** (geseed met 30 bekende tools) + `profile_tool` M2M (spiegelt het
  tag-systeem). Vrij toevoegen van een tool die nog niet in de catalogus zit werkt (dedup op slug).
- **Filteren op tool/toolset** in de ledengids + de concierge (`surface(members_grid)` met `tool`-param);
  de tool-zoekintent levert nu ook de tools per maker terug.
- **Logo's** best-effort opgehaald (favicon/og:image) via een nachtelijke job `app.jobs.enrich_tool_logos`
  (toegevoegd aan de runner); nette letter-tile-fallback tot een logo er is. **SSRF-guard** op de logo-fetch
  (privé/loopback/link-local IP's geweigerd, redirects per hop gevalideerd — geldt ook voor og:image/icon-
  kandidaten).
- **AVG**: `profile_tool`-koppelrijen mee gewist bij account-verwijdering (de gedeelde `tool`-master blijft);
  DB-cascade bewezen op Postgres. Migraties `0017_tool_profile_tool` + `0018_seed_tools` (additief, idempotente
  seed, Postgres-pariteit bewezen).
- Gebouwd via een ultracode-workflow (map → implement → adversarieel review); 4 majors + cleanups uit het
  review verwerkt. 557 tests groen.

## [0.35.0] - 2026-06-20
### Changed — fal.ai-sfeerbeeld reflecteert nu écht het profiel
- **Cover-art-director** (`cover_art_service.build_prompt`): de oude prompt plakte rauwe bio-tekst in een vaste
  kosmische stijl (een beeldmodel maakt daar generieke nevels van). Nu vertaalt één goedkope Claude-call de
  essentie van het profiel (headline, wat je maakt, projecten, onderwerpen) naar een CONCRETE visuele metafoor
  (bv. voice-agents → "soundwaves dissolving into a constellation"), gezet in het vaste kosmische stijl-anker
  (deep indigo/glow, geen tekst/gezichten/logo's). Het sfeerbeeld wordt zo persoonlijk én blijft on-brand.
- Gegrond + best-effort: gegated op `AI_ENRICH_ENABLED`; bij uit/leeg/fout terug naar de deterministische
  `cover_prompt`. Raakt zowel de handmatige "Nieuwe cover" als de automatische cover na de profielbouw (één
  chokepoint, `POST /profiel/ai/cover`). 544 tests groen.

## [0.34.0] - 2026-06-19
### Added — een nieuw project wordt nu direct verrijkt (niet pas 's nachts)
- **Async-na-opslaan**: zodra je een project met een link toevoegt of de link wijzigt (inline-editor),
  start de verrijking (screenshot-hero + samenvatting) meteen in een achtergrond-thread — geen vertraging op
  de bewerk-UX. `project_enrich_service.trigger_async` (gegated op Cloudflare-creds; dubbel-werk-guard via een
  in-proces `_inflight`-set; eigen sessie per thread).
- **Lazy-on-first-view** (universeel vangnet): opent iemand een projectpagina die nog een screenshot/samenvatting
  mist, dan start de verrijking ook — dekt projecten uit álle aanmaakpaden (concierge-draft, AI-bouwer, MCP).
- **Guard**: `enrich_offering` genereert alleen wat ontbreekt (geen dubbele CF/Claude-call); een URL-wijziging
  ruimt het oude screenshot-bestand op en nult beide velden → schone her-generatie. Nachtelijke job blijft de
  laatste backstop. 540 tests groen.

## [0.33.1] - 2026-06-19
### Fixed
- **Screenshot-422 op sommige sites**: de hero-screenshot wachtte op `networkidle0`, wat veel moderne sites
  (analytics/polling) nooit bereiken → Cloudflare gaf 422 (8/9 projecten lukten, 1 faalde). Nu `waitUntil:"load"`
  — robuust genoeg voor een hero. De enrich-job pikt de gemiste screenshot vanzelf op (idempotent: `screenshot_url`
  was nog NULL). End-to-end geverifieerd op preview met echte Cloudflare Browser Rendering + Claude.

## [0.33.0] - 2026-06-19
### Added — projectpagina's: screenshot-hero + inhoudelijke samenvatting
- **Elke projectpagina (`/projecten/{slug}`) krijgt automatisch een screenshot-hero van de live site én een
  gegronde AI-samenvatting van de pagina-inhoud.** Beide uit de link van het lid, via **Cloudflare Browser
  Rendering** (`browser_render_service`): `/screenshot` → WEBP-hero, `/markdown` → pagina-tekst die een gewone
  Claude-call samenvat (geen web_fetch/pause_turn-server-tools → ontwijkt de SDK-valkuil). CF haalt de externe
  pagina op (geen SSRF vanuit ons).
- **Datamodel**: `offering.screenshot_url` (hero, valt terug op het bestaande `image_url`) + `offering.summary`
  (los van de door het lid getypte `description`). Migratie `0016` (additief/nullable, Postgres-pariteit bewezen).
- **Verrijking via de nachtelijke job** `app.jobs.enrich_projects` (toegevoegd aan `nightly-jobs.sh`): idempotent
  (alleen projecten met URL én ontbrekende verrijking), gegated — samenvatting op `AI_ENRICH_ENABLED`, screenshot
  op CF-creds. Bij een URL-wijziging nult `update_offering` screenshot+summary → her-genereren voor de nieuwe link.
- Hero + Samenvatting gerenderd in `projects/view.html`; og:image/seo_desc gebruiken nu de screenshot/samenvatting.
- 536 tests groen. **Let op**: de CF-token heeft de **Browser Rendering**-permissie nodig (dashboard).

## [0.32.1] - 2026-06-19
### Added — nachtelijke job-runner (scheduling-gat gedicht)
- **`scripts/nightly-jobs.sh`**: draait nachtelijk `refresh_matches` (matchsuggesties) + `distill_memories`
  (concierge-geheugen) op de M4. Beide gegated op `AI_ENRICH_ENABLED`, idempotent, lage op-last; bewust geen
  `set -e` zodat een fout in job 1 job 2 niet blokkeert. Aangeroepen door de LaunchAgent
  `com.theuws.dewereldvan.nightly-jobs` (machine-config op server-mini). Hiermee groeit het geheugen en
  verversen matches voortaan vanzelf, unattended.

## [0.32.0] - 2026-06-19
### Changed — Concierge-intelligentie Fase 3: één shell voor ingelogde leden
- **Einde van de twee paradigma's.** Een ingelogd, goedgekeurd lid kreeg op de klassieke kosmische
  pagina's nog het volledige `_cosmic_nav`-sectiemenu náást de agent-canvas. Nu krijgt zo'n lid een
  minimale shell-nav (brand → canvas + "Vraag de wereld"-ingang + admin-`Beheer`); de canvas/concierge
  is de navigatie. Anoniem/publiek houdt de volledige crawlbare voordeur-nav (ontdekken + login/register + SEO).
- **Footer-fallback overal als a11y/no-JS-vangnet.** Waar de nav het sectiemenu nu verbergt, rendert
  `_concierge.html` de bestaande footer-fallback (échte `<a href>` + logout-form, no-JS-zichtbaar) — één
  keer (op de canvas bezit de shell 'm al). Fallback aangevuld met Agenda, Nieuws en Verbind tool.
- Geen migratie (template-only). 524 tests groen incl. nav-states (anon volledig, lid minimaal + fallback,
  admin houdt Beheer, canvas heeft precies één fallback). PRD: `docs/PRD-concierge-intelligentie.md` (Fase 3).

## [0.31.0] - 2026-06-19
### Added — Concierge-intelligentie Fase 2: sessie-overstijgend geheugen
- **De concierge onthoudt nu wie je bent over sessies heen.** Een compact, AI-gedistilleerd geheugen
  (`member.member_memory`) over wat je maakt, zoekt en kunt — opgebouwd uit je eerdere gesprekken en
  geïnjecteerd in de system-prompt, zodat een volgend gesprek meteen persoonlijk is.
- **Periodieke distill i.p.v. synchroon** (`app/services/member_memory_service.py` + job
  `python -m app.jobs.distill_memories`): één goedkope Claude-call per lid met nieuwe turns, gegated op
  `AI_ENRICH_ENABLED`. Bewust een job (zoals `refresh_matches`): een LLM-call in de stream zou de UX
  vertragen en de EventSource sluit op `done`. Idempotent via een hoogwatermerk (`memory_synced_turn_id`).
- **Grounding + injectie-discipline**: het geheugen is achtergrond, expliciet GEEN instructie; alleen
  duurzame, door het lid zelf vertelde feiten — geen chitchat, geen verzinsels.
- **AVG**: het geheugen wordt meegewist bij volledige account-verwijdering (de member-row) én bij het
  wissen van het concierge-gesprek (`clear_turns`). Resetbaar via `member_memory_service.clear`.
- Migratie `0015_member_memory` (additief, dialect-neutraal: Text + Integer nullable; Postgres-pariteit
  bewezen). 520 tests groen. PRD: `docs/PRD-concierge-intelligentie.md` (Fase 2).

## [0.30.0] - 2026-06-19
### Added — Concierge-intelligentie Fase 1: `explain` doorzoekt nu een kennisbank
- **`explain` werd retrieval i.p.v. een vaste 6-topic-dict.** Vragen buiten die 6 onderwerpen gaven
  "onbekend onderwerp" — een wow-killer. Nieuw: `app/services/knowledge.py` (gecureerde corpus van ~15
  fragmenten: toegang, kosten, inloggen zonder wachtwoord, je data wissen, zichtbaarheid, matches, intro's,
  AI-tool koppelen/MCP, agenda, nieuws, profielbouw, demo, ideeën, roadmap) + deterministische
  keyword-retrieval (`search`). Geen LLM, geen dependency, geen pgvector (latere schaal-stap).
- **`explain(query)`** neemt nu een vrije vraag (back-compat: `topic` werkt als query) en geeft de best
  passende gegronde fragmenten terug. 0 hits → een eerlijke `note` (de agent zegt dat hij het niet weet)
  i.p.v. een harde fout. De grounding-poort blijft: de agent synthetiseert alleen uit teruggegeven snippets.
- **SYSTEM_PROMPT** stuurt nu élke "hoe werkt het platform"-vraag naar `explain` met de vraag van het lid.
- **MCP-tool `hoe_werkt_dewereldvan(vraag="")`** gebruikt dezelfde kennisbank (één bron, ook vanuit je editor).
- 508 tests groen (incl. retrieval-scoring, back-compat, eerlijke fallback). PRD: `docs/PRD-concierge-intelligentie.md`.

## [0.29.2] - 2026-06-19
### Fixed — agent-canvas: je vraag + de "verbind"-pagina in beeld
- **Je vraag verdween**: de canvas toonde alleen het antwoord, niet wat je vroeg. De stream rendert nu je
  vraag als bubbel boven het antwoord (`_stream.html`).
- **"Ik breng je er even heen" deed niets**: `/profiel/verbind` was geen surface, dus de agent probeerde
  weg te navigeren (gebeurde niet in de canvas). Nu is **`verbind` een in-canvas surface** — het token-paneel
  (genereer-knop + `claude mcp add`-commando + tokenlijst) materialiseert ónder de chat. Navigate naar
  `/profiel/verbind` mapt naar de surface; de agent gebruikt `surface verbind` i.p.v. navigeren.

## [0.29.1] - 2026-06-19
### Fixed
- **De concierge kon de MCP-koppeling niet uitleggen** (viel buiten de 5 vaste `explain`-onderwerpen →
  "onbekend onderwerp"). Nieuw onderwerp **`verbind`** + synoniemen (`mcp`, `ai-tool`, `claude code`,
  `cursor`, `koppelen`…) met gegronde uitleg + verwijzing naar `/profiel/verbind`; navigate-route `verbind`
  → de tokenpagina; instant-index + SYSTEM_PROMPT kennen het intent. Vraag de agent nu "hoe verbind ik mijn
  AI-tool / wat is de MCP-server" en je krijgt uitleg + de weg ernaartoe.

## [0.29.0] - 2026-06-19
### Added — MCP-server: "praat met dewereldvan vanuit je eigen AI-tool" (activatie)
- **dewereldvan als MCP-server** (FastMCP, Streamable HTTP, stateless), gemount op `/mcp` in de web-
  container. AI-bouwers koppelen 'm aan Claude Code / Cursor / eigen agents en bouwen hun profiel, doorzoeken
  de gids, halen matches op en sturen intro's — **zonder hun editor te verlaten**. Tools: `wie_ben_ik`,
  `werk_profiel_bij`, `voeg_project_toe`, `voeg_zoekvraag_toe`, `zoek_makers`, `mijn_matches`, `stel_voor`,
  `hoe_werkt_dewereldvan`, `bouw_profiel_uit_link` (AI trekt je profiel uit een link). Dunne laag over de
  bestaande services; elke tool gescoped tot het geauthenticeerde lid.
- **Persoonlijk Bearer-token** (`PersonalToken`, migratie `0014`): alleen de hash opgeslagen (magic-link-
  patroon), ruwe token één keer getoond, intrekbaar. ASGI-auth-middleware → 401 zonder geldig token; een
  token = "act as dit approved lid", nooit role-escalatie. **"Verbind je AI-tool"-pagina** (`/profiel/verbind`)
  genereert tokens + toont het kant-en-klare `claude mcp add`-commando.
- **Stack gemoderniseerd**: fastapi 0.118 → **0.137.2** (+ starlette 1.x) — vereist door het MCP-ecosysteem
  (sse-starlette ≥0.49). CSRF zondert `/mcp` uit (eigen Bearer-auth). AVG: `PersonalToken` in
  `delete_member_completely`. **Live MCP-handshake lokaal end-to-end geverifieerd** (auth + tools + writes).
  6 nieuwe tests (493 groen + Postgres-pariteit). Telegram rich-content-bot op de roadmap gezet.

## [0.28.0] - 2026-06-19
### Added — Connect/intro (Tier 1 Fase 2): de match wordt verzilverd
- **"Stel me voor" doet eindelijk iets.** Nieuwe `Connection`-entiteit (migratie `0013`): een match-kaart
  heeft nu een **"stel me voor aan …"**-knop → voorgevuld, gegrond intro-bericht → bevestigen → de intro
  wordt **gepersisteerd** en de ontvanger **gemaild** (kosmische `intro.html`-mail, plain/directe taal,
  géén contactgegevens). De match gaat naar `acted`.
- **De ontvanger beslist** (consent-poort): `surface(connections)` toont inkomende + uitgaande intro's;
  inkomend-pending krijgt **Accepteren / Niet nu**. Pas ná **akkoord** delen beide partijen hun e-mail
  (`can_view_contact`). Push-chip "N intro's wachten op jou" (hoogste prioriteit).
- **Geen dood spoor meer**: idempotent (geen dubbele intro from→to), rate-limit (8/uur), e-mail faalt nooit
  silent (intro blijft staan, nette melding). **AVG**: `Connection` in `delete_member_completely` (afzender
  óf ontvanger). `draft`-pad voor de agent + slug-pad ondersteund. 8 nieuwe tests (487 groen + Postgres-pariteit).

## [0.27.0] - 2026-06-19
### Added — Matchmaking vraag↔aanbod (Tier 1, Fase 1): de kern-visie gaat werken
- **De `Need` doet eindelijk werk.** Nieuwe `MatchSuggestion`-entiteit (migratie `0012`) koppelt andermans
  `Need` aan jouw `Offering`. Twee-traps engine (`match_service`, fork A): goedkope SQL-kandidaatgeneratie
  (gedeelde tags + woord-overlap, gecapt) → **één Claude-call per need** die op échte complementariteit
  oordeelt + een gegronde "waarom"-zin schrijft (forced tool-use, geen `parse()`; grounding-poort: alleen
  aangeboden offering-ids komen door). Gegated op `AI_ENRICH_ENABLED` — uit = geen call, geen suggesties.
- **Matchbereik: alle goedgekeurde leden** (fork A), incl. members-only profielen (besloten community →
  interne waarde; contact pas na intro-accept in Fase 2).
- **`surface(matches)`** in de agent-canvas: "wat is er voor mij?" / "laat mijn matches zien" → kosmische
  match-kaarten met de waarom-zin prominent + score + perspectief (jij zoekt ↔ iemand zoekt wat jij maakt).
  Tonen markeert `new → seen`.
- **Push-chip** (fork A): "N nieuwe matches voor jou" verschijnt ongevraagd bovenaan de canvas-chips
  (hoogste prioriteit, pure SQL op `status=new`).
- **Idempotent + sticky**: uniek `(need_id, offering_id)`; `dismissed`/`acted` blijven gerespecteerd bij
  herrekenen. **AVG**: `MatchSuggestion` in `delete_member_completely` (zoeker óf maker). Cron-job
  `python -m app.jobs.refresh_matches`. 9 nieuwe tests (479 groen + 4 Postgres-pariteit geskipt).

## [0.26.0] - 2026-06-19
### Added — Tier 0 asset-bescherming (uit de audit): backups + Postgres-testketen
- **Nightly Postgres-backup** — dewereldvan geregistreerd in het bestaande, beproefde M1-backupsysteem
  (`m4-backup.sh`, 02:00 LaunchAgent): logische `pg_dump` + gzip + size-validatie + daily/weekly-retentie
  (7d/4w) + ntfy-alerting + M4-heartbeat. Augment van een werkend systeem, geen parallelle stack. De audit
  meldde "geen backup"; de waarheid bleek "nooit aangemeld". **Restore end-to-end bewezen**: dump → gzip →
  restore in wegwerp-Postgres, rij-aantallen identiek aan live. Procedure: `docs/BACKUP-RESTORE.md`.
- **Postgres in de testketen** — `tests/test_postgres_parity.py` draait `alembic upgrade head` + smoke-CRUD
  tegen een ECHTE Postgres (default geskipt; de snelle SQLite-suite blijft standaard). Vangt de dialect-bug-
  klasse die 0008 (varchar te kort) én 0010 (boolean-default) door de SQLite-tests liet glippen en pas in
  productie faalde. **Bewezen**: met de 0010-bug terug → rood met exact `DatatypeMismatch`; na fix → groen.
- **Lokale runner** `scripts/test-postgres.sh` (wegwerp-Postgres in Docker) + **CI-workflow**
  `.github/workflows/ci.yml` (SQLite-suite + Postgres-pariteit via een `postgres:16`-service) → dialect-bugs
  worden rood vóór deploy i.p.v. via een handmatige prod-browsertest. 470 groen + 4 geskipt (pariteit).

## [0.25.1] - 2026-06-19
### Fixed
- **Migratie `0010_post` faalde op Postgres** (`hidden` boolean met `server_default=sa.text("0")` →
  DatatypeMismatch). Nu `sa.false()` (dialect-neutraal, projectconventie). De SQLite-migratietest ving dit
  niet; CREATE TABLE faalde atomair (geen partial state). Preview-redeploy hersteld.

## [0.25.0] - 2026-06-19
### Added — Agenda & Nieuws (Fase 2): verweven in de agent-shell
- **`surface(agenda)` + `surface(nieuws)`**: "wat is er te doen?" / "laat de agenda zien" / "wat is er
  verschenen?" materialiseren de agenda/nieuws-lijst **in-canvas** (geen paginawissel), server-side uit de
  DB gerenderd (grounding-poort). `navigate /agenda|/nieuws` mapt ook naar deze surfaces.
- **`draft_event` + `draft_news`** schrijf-tools (tonen + 1-klik bevestigen): "zet een meetup in de
  agenda …" / "ik werd geïnterviewd, deel dit …" → de agent SCHRIJFT NIET maar geeft een gevalideerd
  `{draft, fields}`-signaal; de router rendert het echte voorgevulde formulier dat naar het bestaande
  `POST /agenda`·`/nieuws`-endpoint commit (CSRF + Pydantic + rate-limit). Lopen door dezelfde
  surface-machinerie als de andere schrijf-surfaces.
- Instant-index + SYSTEM_PROMPT uitgebreid met agenda/nieuws-intents. 6 nieuwe tests (470 groen).

## [0.24.0] - 2026-06-19
### Added — Agenda & Nieuws (Fase 1): iedereen publiceert direct
- **Eén holistische `Post`-entiteit** (`kind` ∈ event | nieuws, + later "etc") i.p.v. losse tabellen:
  gedeelde velden (titel/omschrijving/link/hidden) + type-specifieke nullable velden. Lage op-last bij
  groei (één router, één rate-limit, één admin-verberg, één AVG-hook). Migratie `0010_post`.
- **`/agenda`** — kosmische meetup-kaarten met prominente, kleur-gecodeerde **frequentie-badge**
  (terugkerend = cyaan/levend met pulse, eenmalig = goud) + **eerstvolgende-countdown** ("over 3 dagen").
  Aankomend-eerst gesorteerd. Altijd-zichtbare "iedereen voegt toe"-uitnodiging; lege staat = die
  uitnodiging groot.
- **`/nieuws`** — artikelen/interviews/uitgelicht werk van leden, nieuwste-eerst, met een kleine
  **rol-badge** (zelf geschreven / geïnterviewd / uitgelicht / gedeeld). Link verplicht.
- **Iedereen plaatst direct zichtbaar** (geen goedkeuringswachtrij, fork A); admin kan **verbergen**
  (`hidden`, spiegelt ideeën-moderatie + AuditLog). Per-lid rate-limit (10/uur, gedeeld over events+nieuws).
- **AVG**: `Post.added_by_id` is **SET NULL** → een community-meetup of gedeeld artikel blijft staan als de
  toevoeger zijn account wist; opgenomen in `delete_member_completely`.
- **Gegronde seed** (prod-only, idempotent, migratie `0011`): **Aimelo** (opgehaald van aimelo.nl — elke
  woensdag 18:00–20:00, Almelo, eerstvolgend wo 24 juni) + **meetup Meppel/Zwolle** (als te-bevestigen
  gemarkeerd). Plus **roadmap-cachet**: 9 voorbeeld-roadmap-items met statussen.
- Nav uitgebreid (Agenda + Nieuws); `relatieve_tijd`/`nl_datum` Jinja-filters. 18 nieuwe tests (464 groen).

## [0.23.0] - 2026-06-19
### Changed (demo-startknop) + Fixed (materialisatie-cleanup)
- **Demo speelt pas ná een klik**: `/demo` heeft nu een prominente "▶ Speel de demo af"-knop. De demo
  speelde eerder meteen bij paginalaadt → leek een gewone laad i.p.v. een demo. Nu zie je 'm vóór je
  ogen bouwen (rustiger pacing) ná de klik.
- **`field--materializing`-cleanup**: bij outerHTML-slot-swaps is `htmx:afterSwap`'s `e.target` de ouder,
  niet de verse slot — dus de class bleef hangen. Nu zoeken we de verse slots binnen root en ruimen hun
  class op na de animatie (`field--ready`).

## [0.22.3] - 2026-06-19
### Fixed
- Auto-cover aan het `f-*`-materialisatie-event gehangen (het `done`-event triggerde de listener niet
  betrouwbaar door `sse-close`).

## [0.22.2] - 2026-06-19
### Fixed
- Builder = singleton (elke "Bouw mijn profiel"-klik maakte een tweede builder → dubbele ids braken de
  materialisatie/auto-cover); Enter in de builder-textarea submit nu (Shift+Enter = nieuwe regel).

## [0.22.1] - 2026-06-19
### Fixed (lege profielbouw-regressie + betrouwbare auto-cover)
- **Regressie (v0.21.0): de profielbouw kwam leeg terug.** De "kort + plat"-tekstinstructie zat in
  `SYSTEM_PROMPT`, die óók de finalize/structured-output-call voedt → het model vulde lege velden.
  Verplaatst naar een aparte `STREAM_TEXT_INSTRUCTION` die ALLEEN de streamende conversatie-call raakt;
  de finalize-call krijgt de oorspronkelijke prompt terug → velden vullen weer.
- **Auto-cover betrouwbaar**: het `done`-SSE-event triggerde de auto-cover niet (htmx-ext-sse sluit via
  `sse-close` vóór de listener). Nu gekoppeld aan het veld-materialisatie-event met een debounce — vuurt
  alleen bij een gevulde build, één keer (vlag + img-check).

## [0.22.0] - 2026-06-19
### Changed (sfeerbeeld nu automatisch)
- Ná de profielbouw genereert de AI nu **automatisch** een sfeerbeeld (fal.ai) — één keer per build,
  niet per bericht (vlag + img-check voorkomen herhaling). Hergebruikt de bestaande cover-knop/CSRF; de
  "Nieuwe cover"-knop blijft voor handmatig vervangen. Copy aangepast.

## [0.21.0] - 2026-06-19
### Added (nette AI-formatting · fal.ai-cover in de builder · rijkere demo)
- **AI-antwoorden netjes geformatteerd**: een kleine, veilige markdown-renderer (`static/md.js`) rendert
  de antwoordbubbel op `done` (koppen/bold/lijsten/hr) i.p.v. kale `##`/`**`. Plus prompt-fix: de
  profielbouw-tekst is nu KORT + plat (geen markdown-dump van het hele profiel — de velden tonen het al).
- **fal.ai verfraait het profiel**: de cover-generatie (`/profiel/ai/cover`, fal.ai flux/schnell) zat
  wél in de code maar nergens in de flow. Nu staat de "✦ sfeerbeeld — door AI"-sectie in de
  canvas-builder (één klik → een gegenereerd sfeerbeeld dat zich aanpast op wat je maakt).
- **Rijkere publieke demo**: `/demo` toont nu een écht door fal.ai gegenereerd sfeerbeeld
  (`static/demo-nova-cover.jpg`), een tijdlijn en een "andere makers"-teaser (fictief). 446 tests groen.

## [0.20.0] - 2026-06-19
### Added (publieke demo/showcase — gescript, fictief, "door AI gemaakt")
PRD: `docs/PRD-publieke-demo.md` (variant A). Publieke route `GET /demo` (geen login, indexeerbaar):
een gescripte replay die een **fictief** makersprofiel (Nova Belmonte, fictieve site `studio-nova.ai`)
in-materialiseert met exact dezelfde kosmische esthetiek (`field--materialize`) — **geen AI-call, geen
DB**, nul kosten/misbruik. Permanente "✦ Demo — fictief profiel, door AI opgebouwd"-badge + CTA → `/register`.
Reduced-motion + no-JS tonen de inhoud direct.

### Fixed (first-run "Bouw mijn profiel" deed niets)
- De first-run-CTA vulde het veld en liet de **LLM** de tool kiezen — die koos soms `my_status` + tekst
  i.p.v. `surface(profile_builder)`, dus de builder opende niet. Nu opent de CTA de builder
  **deterministisch** via `GET /concierge/profielbouw` (rendert de profile_builder-surface direct, zonder
  tool-gok). Altijd raak.

## [0.19.0] - 2026-06-19
### Added (schrijf-surfaces Fase 2.2 — profiel-tekstvelden draften vanuit het gesprek)
- **`draft_field`-tool** (`headline`/`bio`): "verander mijn kopregel naar …" / "pas mijn bio aan …" →
  de agent stelt een voorgevulde nieuwe waarde voor; het lid bevestigt en het bestaande
  `PATCH /profiel/ai/veld/{naam}` (whitelist `_TEXT_FIELDS` + maxlen + CSRF) commit. Zelfde
  tonen-+-bevestigen-mechanisme als de offering/need/idee-drafts.
- **Bewust gescopet**: `seeking` (overlapt met `draft_need` — de primaire need) en `tags` (vereist
  append-semantiek; de agent kent de huidige tags niet) schuiven door naar later. 443 tests groen.

## [0.18.0] - 2026-06-19
### Added (schrijf-surfaces Fase 2.1 — de agent voert ledenacties uit, "tonen + 1-klik bevestigen")
PRD: `docs/PRD-schrijf-surfaces.md` (variant A: constructief). De agent kan nu ledenacties
**voorbereiden** maar nooit zelf wegschrijven.
- **Draft-tools + vaste `DRAFT_REGISTRY`**: `draft_offering`/`draft_need`/`draft_idea`. De tool
  SCHRIJFT NIET; ze geeft een gevalideerd `{draft, fields}`-signaal (str-whitelist per entiteit). De
  router rendert het **échte voorgevulde formulier** in de stroom; het lid past evt. aan en klikt
  bevestig; het **bestaande** endpoint (`POST /profiel/offering` · `/profiel/need` · `/ideeen`) commit
  met zijn Pydantic-schema + CSRF + rate-limit. Eén schrijf-pad, één stramien per entiteit.
- Drafts lopen door dezelfde surface-machinerie (één kanaal/event), met een `{draft, fields}`-payload.
  "laat maar" sluit het concept zonder iets op te slaan (geen write zonder klik).
- **Buiten scope (AVG)**: zichtbaarheid-openbaar + verwijderen blijven dedicated (consent-poort); de
  agent draft ze niet, hij verwijst ernaar.
- System-prompt leert de agent draften (voorstellen op basis van wat het lid zei, niet opslaan).
- Tests: registry-grens + veld-whitelist, draft-emit-zonder-write, voorgevulde partials posten naar de
  echte endpoints. 439 tests groen.

## [0.17.0] - 2026-06-19
### Added (first-run discovery — profielbouw vindbaar zonder uitleg)
- **First-run-aanbod in de canvas**: een lid zonder (compleet) profiel krijgt één rustig, inline aanbod
  ("Zal ik je profiel opbouwen? Heb je een website? Dan scan ik die vast…") met een CTA die de
  profielbouw-surface in de stroom opent (`data-canvas-ask`). Geen pop-up; verdwijnt zodra het profiel
  compleet is (gegated op `completeness`). Lost op dat een nieuw lid niet wíst dat het de agent om
  profielbouw kon vragen.
- De chips blijven puur ontdek-laag (makers/roadmap/tag-overlap); de profielbouw-chip-naar-de-pagina is
  vervangen door het in-canvas aanbod. 434 tests groen.

## [0.16.0] - 2026-06-19
### Added (conversationele profielbouw in de canvas — variant A, eerste deel)
PRD: `docs/PRD-conversationele-profielbouw.md`. Doel: profielbouw mag niet voelen als werk.
- **`profile_builder`-surface**: de levende profielbouw start nu ÍN de canvas (geen paginawissel) —
  de agent materialiseert de builder in-stroom. Hergebruikt de bestaande `ai_profile`-materialisatie
  1:1 (`#materialisatie`-host + `#profielvorm` + `/profiel/ai/bericht`), zónder de
  publiceer-/reset-/verwijder-beheerblokken (progressive disclosure — die blijven op de volledige
  bewerkpagina, één klik weg). Drempel-verlagende opener: *"Heb je een website? Dan scan ik die vast om
  te weten wie je bent…"* (één link i.p.v. een formulier).
- **Agent-tuning**: de system-prompt kent nu de `surface`-tool en de regel dat een brede toon-intent
  GEEN filter vraagt — "laat de makers zien" → `surface(members_grid)` zonder filter; "bouw mijn
  profiel" → `surface(profile_builder)`. Lost de live-waargenomen tegenstrijdigheid op ("ik kan niet
  zonder filter" + tóch een kaart).
- Tests voor de `profile_builder`-loader (lid → builder-template; anon → niets). 432 tests groen.

## [0.15.1] - 2026-06-19
### Fixed (canvas-chat: dubbele rand + verdwijnende reply — live op preview gevangen)
- **Dubbele border om het invoerveld**: de globale `.cosmic input`-regel (border + background +
  eigen cyan focus-border) overschreef `.concierge-form__input` → het veld kreeg een eigen rand
  bovenop de form-frame. Opgelost: input-regel specifieker (`.cosmic .concierge-form__input` + `:focus`)
  zodat het veld kaal is en de form de enige rand levert; de harde `0 0 0 4px` focus-ring werd één
  zachte halo.
- **Reply verdween zodra de stream klaar was**: het `done`-event ruimde de hele SSE-host op
  (`#csse-…`, inclusief het antwoord-tekstblok). Nu verwijdert `done` alléén het transiënte
  reasoning-paneel (`#reasoning-…`); het antwoord + de gematerialiseerde kaarten/surfaces blijven staan.

## [0.15.0] - 2026-06-19
### Added (Agent-Shell Fase 1 — de agent wordt de shell)
De grootste pivot tot nu toe: voor **ingelogde, goedgekeurde leden** is de site geen website-met-
navigatie meer maar een **levende agent-canvas**. Geen menu, geen links — je landt direct in de stroom,
typt een vraag, en interfaces (ledengrid, makerkaart, ideeën, roadmap) **materialiseren in-stroom**.
De anonieme/publieke kant houdt de klassieke crawlbare pagina's (showcase/SEO + publieke launch blijven
heel). Eén engine, één kosmische identiteit — dit is een AUGMENT van de bestaande concierge, geen tweede stack.
PRD: `docs/PRD-agent-shell.md`; build-spec: `docs/SPEC-agent-shell-fase1.md` (understand→design→red-team,
6 blockers gesloten).

- **`surface`-tool + vaste `SURFACE_REGISTRY`** (`concierge_service.py`): de agent materialiseert een
  interface uit een **vaste registry** (members_grid/member_detail/ideas_list/roadmap_board/profile_view) —
  het "gezet stramien per entiteit" tegen wildgroei. De engine produceert NOOIT HTML; ze stuurt een
  gevalideerd `{view, params}`-signaal, de **router rendert server-side uit de DB** (grounding-poort
  ongewijzigd). Param-keys whitelisted; alleen `str`/`int` door. Opus-4.8-contract onaangeroerd.
- **Generiek `surface`-SSE-event** (`routers/concierge.py`): `_render_surface_by_signal` rendert elk
  geregistreerd fragment in een **eigen `SessionLocal`** (thread-safe), in precies één
  `<section class="surface-card">`-node. `navigate` wordt voor leden **in-stroom render** i.p.v.
  paginawissel (`_nav_to_surface`, incl. `/leden/{slug}`); lege render valt terug op echte navigate.
- **Persistente conversatie-state** (`concierge_state.py` + `concierge_turn`-tabel, migratie `0009`):
  de agent houdt context over meerdere acties. **History-discipline**: nooit een lege/whitespace of
  niet-`str` turn opgeslagen (voorkomt het permanente-400-vergiftigingspad bij refusal/tool-use-turns).
  AVG: `concierge_turn` wordt expliciet gewist in `delete_member_completely`.
- **Agent-canvas-shell** (`concierge/_canvas.html`): standalone kosmisch document zónder hoofdnav,
  `noindex`, htmx+sse synchroon geladen, host mét `hx-ext="sse"`, zichtbaar primair invoerveld,
  één live-region (niet op `<main>`). De root-route (`/`) kiest de shell op login+approved-state.
- **Contextuele suggestie-chips** (`select_chips` + `GET /concierge/chips` + `_chips.html`): de
  "wegwijs zonder menu" — pure SQL, ≤3 gegronde chips die de agent aanspreken (in-stroom) of een echte
  link zijn; ververst na elk antwoord.
- **Subtiele footer-fallback** (`concierge/_footer_fallback.html`): één klein glyph → ingetogen menu met
  **echte `<a href>`/form-POST** dat de agent **omzeilt** — a11y-vangnet + faal-vangnet (werkt zonder
  agent/SSE/JS) + discoverability. Admins houden hier de `Beheer`-link (goedkeur-queue).
- **Tests** (`test_agent_shell_fase1.py` + uitbreidingen): registry-grens, param-whitelist/coercion,
  single-node surface, grounding (besloten/verzonnen slug → niets), history-discipline, dual-shell-
  routing (approved→canvas, pending→voordeur, admin→canvas+Beheer), single-host, `hx-ext`, één
  live-region, footer-hrefs+`<noscript>`, `navigate→surface`, chip-selectie, surface-emit, AVG-wis,
  `0009`-migratie round-trip. **430 tests groen.**

## [0.14.2] - 2026-06-18
### Added (kosmische invite-mail — zelfde stijl als de magic-link-mails)
- **`emails/invite.html` + `render_invite()`**: de groep-invite-mail krijgt nu de verzorgde kosmische
  HTML (gouden pill-CTA "Maak je profiel ✦", serif-heading, donkere nebula-shell, Gmail-safe inline-CSS) —
  exact dezelfde vormgeving als de magic-link/goedkeurings-mails, met de AVG-regel ("één klik wist alles")
  en de persoonlijke afsluiter. (Was eerst kale tekst — de eerste indruk verdient de mooiste mail.)
- **Bekend: uitgaande mail naar externe adressen staat nog UIT bij Cloudflare** (`email.sending.error.
  email.sending_disabled`, 403/code 10203). Verzending naar de wachtlijst kan pas na activatie (CF-dashboard:
  Email Sending aanzetten + verzenddomein onboarden/SPF-DKIM + token-scope) of via een andere ESP (Resend-
  adapter bestaat al). Zie `dewereldvan-cloudflare-email` memory.

## [0.14.1] - 2026-06-18
### Fixed (live-test groep-invite — Postgres varchar-truncatie)
- **Registreren via de invite-link gaf een 500 op Postgres**: `audit_log.action` was VARCHAR(18) (ooit
  gesized op de langste enum-waarde), maar de nieuwe audit-actie `invite_registration` is 19 tekens →
  `StringDataRightTruncation`. SQLite negeert varchar-lengtes en miste het in de tests; de live browser-test
  ving het. Fix: migratie `0008` verbreedt de kolom naar VARCHAR(64) (dialect-bewust; SQLite no-op) en het
  ORM-model zet nu expliciet `length=64` zodat een nieuwe audit-actie niet stil afkapt.

## [0.14.0] - 2026-06-18
### Added (volledige profielverwijdering — data-regie, AVG)
- **"Wis mijn profiel volledig"**: een prominente, altijd-bereikbare knop (op `/profiel/bewerken` én de
  AI-bouwpagina) → één heldere bevestiging → `POST /profiel/verwijderen` wist het lid + ALLES wat eraan hangt
  **definitief** en logt uit, met een kosmische afscheidspagina (`/profiel/gewist`).
- `account_deletion.delete_member_completely`: verwijdert expliciet (DB-agnostisch, FK-veilige volgorde) het
  foto-bestand op schijf, profiel + offerings (+ slug-historie) + needs + profile_links + tag-koppelingen
  (níét de gedeelde tags), ideeën + stemmen (ook cross-member), feedback, nudge-dismissals, AI-gesprekken,
  magic-link-tokens, en de member-row. Bestaande audit-/invite-refs worden genuld; één PII-loze `member_deleted`-
  audit-rij blijft als minimale grondslag-traceability. **Compleetheids-test bewijst: geen wees-data, gedeelde
  tags + andere leden intact.** 399 tests groen (10 nieuwe). Geen migratie nodig (bestaande SET NULL-FK's).

## [0.13.0] - 2026-06-18
### Added (groep-invite-link — directe profiel-aanmaak voor genodigden)
- **Deelbare groep-invite-link** (PRD-verificatie-links §0): één link (`/uitnodiging/{token}`) die in de
  WhatsApp-groep gedeeld kan worden; wie 'm opent maakt **direct** een profiel — pre-approved (geen admin-
  queue), 24 uur geldig, regenereerbaar door een admin (`/admin/uitnodiging` toont + roteert de link).
- Veilig: token `secrets.token_urlsafe(32)`, 24u TTL, regenereerbaar (gelekte link te doden), CSRF, IP-rate-
  limit op nieuwe inschrijvingen, 410 op dood token, noindex landing. De link verleent **uitsluitend**
  approved-lidmaatschap — nooit admin (admin alleen via `ADMIN_EMAILS`); geschorst/geweigerd wordt niet heropend.
- Alembic `0007_group_invite` (additief). 390 tests groen (24 nieuwe).

## [0.12.1] - 2026-06-18
### Fixed (concierge live-test — SSE connect overal)
- **De concierge-stream opende nooit** op de meeste pagina's: `htmx-ext-sse` (en op sommige pagina's
  zelfs `htmx` zelf) werd alleen in de profielbouw-head geladen, niet op de andere kosmische pagina's.
  Daardoor was `hx-ext="sse"` op `#concierge-materialisatie` een no-op → geen EventSource → het paneel
  bleef hangen op "AI aan het werk" (geverifieerd via live browser-test: geen `GET /concierge/stream`).
  Fix: een idempotente bootstrap-loader in `_concierge.html` (de cross-cutting include) laadt htmx +
  htmx-ext-sse waar ze ontbreken — dekt alle 18 concierge-pagina's op één plek.

## [0.12.0] - 2026-06-18
### Added (de Concierge — een gegronde, intelligente laag overal)
- **AI-concierge als ruggengraat** (`docs/PRD-concierge.md`, APPROVED): een intent-oppervlak (⌘K / `/` /
  "✦ Vraag de wereld"-veld in de nav — geen chatbot-bubbel) dat overal oproepbaar is. Een instant-laag
  (geen AI, client-side route/maker-match) + een AI-stream die het profielbouw-patroon 1:1 hergebruikt:
  reasoning-glow, tool-status, woord-voor-woord tekst, en **echte, klikbare makerkaarten die materialiseren**.
- **5 gegronde function-tools** (`concierge_service`): `search_members`/`navigate`/`connect`/`explain`/`my_status`.
  Harde anti-hallucinatie: kaarten worden server-side uit de DB op slug gerenderd → een verzonnen naam levert
  géén kaart. AVG-poort zit in de bron (alleen public+approved). Opus 4.8-contract + MAX_TOOL_TURNS-cap.
- **Proactieve laag** (`nudge_service`, pure SQL): max één gegronde suggestie, alléén wanneer je het oppervlak
  zelf opent, 30 dagen dismissbaar. Anon krijgt alleen de neutrale "N nieuwe makers"-nudge.
- **PREVIEW-banner** (besloten preview, alleen op uitnodiging) cross-cutting op alle pagina's.
- **Founder-herkenning**: Bart Ensink / Hendrik van Zwol worden bij registratie herkend (`is_founder`) en de
  concierge nodigt hen éénmalig uit hun **ontstaansverhaal** te vertellen (`member.origin_story`).
- Alembic `0006_concierge` (additief: `is_founder`, `origin_story`, `concierge_nudge_dismissal`).
### Fixed (integratie-review — backend↔frontend-naad)
- Wiring-mismatches die de proactieve laag/founder-welkomst/navigatie dood maakten (dismiss-veldnaam,
  ontbrekende nudge-injectie via `GET /concierge/nudge`, drie founder-sleutel-spellingen, instant-`routes`-key,
  `display_name`↔`name`) gerepareerd. **DB-sessie-race** opgelost: kaarten renderen in een eigen `SessionLocal`,
  niet de request-db vanuit de drain-thread. `navigate` emit nu een SSE-event (met open-redirect-guard).
- 371 tests groen (incl. 13 nieuwe naad-tests die de gerenderde payloads dekken). Grounding/AVG/injectie/refusal/
  CSRF/Opus-contract: alle reviews PASS.

## [0.11.1] - 2026-06-18
### Changed (frontend volledig kosmisch — funnel launch-klaar)
- **Resterende lichte pagina's gekosmiseerd**: de hele auth-funnel (`/login`, `/register` + verstuurd/
  fout/klaar-schermen), `404`/`500`, `/profiel/bewerken` en `/admin/queue` (+ partials) zijn nu standalone
  kosmische documenten — functie (forms, htmx, CSRF, anti-enumeratie, SEO) volledig intact.
- **Detail-laag**: favicon (kosmische ✦, svg + multi-size ico) + `theme-color`, default OG-kaart (1200×630)
  op publieke pagina's, en de "1 maker"-microcopy-nit (enkelvoud/meervoud) opgelost.
- **Dode code verwijderd**: `base.html` (lichte Tailwind-shell), `_flash.html`, `app.css` — de enige
  resterende emerald/slate-restanten; geen template extend't of rendert ze nog. Voorkomt licht-thema-regressie.
- Transactionele e-mails geverifieerd (al inline/Gmail-safe; geen wijziging nodig). 302 tests groen,
  styleguide + correctheid PASS. Eén bewuste uitzondering: `/admin/feedback` (admin-only) blijft licht — losse follow-up.

## [0.11.0] - 2026-06-18
### Added (kosmische voordeur + innovatieve navigatie + speelveld-samenhang)
- **Kosmische home (`/`)**: de lichte "De wereld van ons"-landing vervangen door een standalone
  `<body class="cosmic">`-voordeur met levend sterrenveld, getrapte entree, en speelveld-poortkaarten
  (3 anon / 4 ingelogd) + één echt signaal (aantal publieke makers) + constellatie-preview bij ≥3 leden.
  Werkt voor anon (uitnodigend) én ingelogd (voordeur naar het speelveld). SEO-indexeerbaar.
- **Innovatieve hoofdnavigatie** (`_cosmic_nav.html`): één herbruikbare, kosmische nav (Makers/Ideeën/
  Roadmap + login/admin-state) met `aria-current`-wayfinding, toetsenbord/mobiel/reduced-motion-veilig.
  Vervangt de ad-hoc `.c-head`-headers op de speelveld-pagina's (`/leden`, `/ideeen`, `/roadmap`,
  profielbouw); publieke detailpagina's houden bewust hun eigen focus.
### Fixed (integratie-review — twee majors)
- **Lege canonical op de home**: de `/`-route gaf geen `canonical` mee → `<link rel="canonical" href="">`.
  Nu `seo_service.canonical_url("/")` (geen self-canonical-regressie).
- **Admin-Beheer-link werkte alleen op `/ideeen`**: de nav las een per-route `is_admin`-context i.p.v. de
  sessie. Nu `request.session.get("is_admin")` (spiegelt `base.html`) → Beheer-link overal, geen lek voor leden.
- Regressietests toegevoegd (canonical-niet-leeg, admin-Beheer-overal, geen-lek-voor-leden). 297 tests groen.

## [0.10.2] - 2026-06-18
### Docs
- **`docs/PRD-verificatie-links.md`** — PRD voor verificatie- & toegangs-links: (a) verificatie-link
  die een lid in de WhatsApp-groep plakt en een admin aanklikt om goed te keuren, (b) e-mail-gebonden
  single-use admin-toekenningslink, (c) wachtlijst-invite. Eén `access_token`-mechanisme bovenop de
  bestaande approval/magic-link-flow; authz + audit + leak-model uitgewerkt. TER BEVESTIGING.

## [0.10.1] - 2026-06-18
### Fixed (live browser-walkthrough op de preview — kern-bug gevangen)
- **Live materialisatie swapte niet in beeld**: het profiel verscheen pas ná een herlaad
  i.p.v. live tijdens/na de stream. Oorzaak: htmx-ext-sse bindt een `sse-swap` alleen aan de
  EventSource op verwerk-moment mét een `sse-connect`-voorouder; de slots in `#profielvorm`
  bestaan al vóór `sse-connect` en bonden daarom nooit (de `done`/`reasoning`-swaps werkten wél
  omdat die vers in het stream-fragment zitten). Fix: de `f-*`-bindingen verplaatst van de
  vooraf-gerenderde slots naar **verse proxy-elementen in `_materialize_stream.html`** (binden
  net als `done`), elk met `hx-target` naar zijn slot — per-veld choreografie + animatie blijven.
  Engine, persistentie en inline-edit waren al correct; alleen de live-swap was stuk.
- **Projecten-volgorde**: `_projects.html` itereert nu `offerings | sort(position)` (review-bevinding #5).
- Geverifieerd op de preview: echte Opus 4.8-generatie uit 5 links → rijk, gegrond profiel dat nu
  live materialiseert (kopregel, 4 projecten, 2 rollen, bio, 10 tags).

## [0.10.0] - 2026-06-18
### Added (AI-profielbouw als één levende flow — VISION-profielbouw uitgevoerd)
- **Levende profielbouw** (`ai/live.html` + slot-partials): je profiel **materialiseert
  zich live in de echte kosmische profielvorm** terwijl je vertelt (per-veld `f-*` SSE-events:
  headline → bio → rollen → projecten → "wat ik zoek" → tags), met de wait-UX (reasoning + per-link
  fetch) eronder. Vervangt de oude 3-staps (chat-bubbels → aparte preview → bewerk-formulier).
- **Volledig inline bijschaven**: klik-op-veld-om-te-bewerken op elk veld (self-swap-patroon),
  met **onzekerheids-markers** op afgeleide velden ("Dit leidde ik af — klopt het?" → Klopt/Aanpassen)
  en "vul aan"-markers op lege velden. Per-veld persist-endpoints voor headline/bio/seeking/tags +
  offerings + rollen (`PATCH`/`POST`/`DELETE`), met eigendoms-check, CSRF en `safe_url`-guard.
- **Nieuwe service**: `profile_link_service` (volledige rol/affiliatie-CRUD) + `profile_service.persist_draft`
  / `update_offering` als één bron van waarheid voor de draft-persist en inline-edit.
- De enrichment/draft-engine (`stream_turn`/`finalize_draft` + alle AVG/hallucinatie-guards) is
  **ongewijzigd hergebruikt**; alleen de ervaring eromheen is nieuw. Spec: `docs/SPEC-living-profielbouw.md`.
### Fixed (integratie-review op de levende flow — adversarieel geverifieerd)
- **Publiceren brak via htmx**: het publiceer-paneel onderschepte de POST en swapte de hele
  303-redirect-body in het mini-paneeltje. Nu: `HX-Redirect` voor htmx (de browser navigeert echt),
  303-fallback voor no-JS.
- **Stille data-loss bij "wat ik zoek"-edit**: het bewerken van `seeking` deed `needs.clear()` en wiste
  via delete-orphan **alle** needs. Nu wordt alleen de primaire need (needs[0]) vervangen.
- **Twee bronnen van waarheid weggewerkt**: de router delegeert nu naar de services (geen inline-duplicaten),
  zodat de service-tests echte productie-code dekken (geen vals-groen). Ongebruikte `update_need` + tests verwijderd.
### Changed
- **Styleguide-gat gedicht**: ontbrekende cosmic.css-classes voor de kaart-edit-overlay, verwijderknop,
  lege-staten en de seeking-kaart toegevoegd (één kosmische look, reduced-motion-veilig).
- De vervangen chat-templates (`build.html`, `_message_sent`, `_chat_message`, `_draft_preview`,
  `_draft_card_link`) verwijderd.
- **Tests**: regressietests voor de htmx-publish, seeking-behoudt-overige-needs en rol-eigendom/kind-guard;
  volledige suite groen (277 passed).

## [0.9.5] - 2026-06-18
### Docs
- **`docs/VISION-profielbouw.md`** — noord-ster voor de profielbouw: het profiel bouwt zichtbaar
  zichzelf terwijl je vertelt, en je verfijnt inline (incl. foto-upload op z'n plek) in één
  doorlopende flow. Vervangt de 3-staps chat→preview→formulier. TER BEVESTIGING.

## [0.9.4] - 2026-06-18
### Fixed (AI-profielbouw — twee blokkerende bugs op productie gediagnosticeerd)
- **Chat brak op beurt 2** ("Er ging iets mis"): teruggespeelde server-tool-blokken
  (web_fetch/code_execution) gaven 400's — eerst ongeldige input-velden (`citations`, dan
  `text`), daarna ontbroken `server_tool_use`-paring na persist/reload. Robuuste fix:
  eerdere beurten worden naar platte tekst gecollapst (`_collapse_history`); de synthese
  blijft, en het model heeft de webtools nog om zo nodig opnieuw op te halen. De zeldzame
  pause_turn-loop binnen één beurt houdt de blokken (vers + gepaard, velden gewhitelist).
- **Draft-generatie faalde altijd**: de code riep `client.messages.parse(output_format=…)`
  aan, dat in de gepinde anthropic-SDK (0.69.0) niet bestaat. `finalize_draft` gebruikt nu
  een **geforceerde tool-call** met `PROFILE_SCHEMA` als `input_schema` + afsluitende
  user-turn (de API eist dat de conversatie op een user-bericht eindigt).
- Volledige flow live geverifieerd: beurt 1 → beurt 2 → draft (headline/rollen/projecten/tags).

## [0.9.3] - 2026-06-18
### Changed
- **Copy-sweep: zweverige taal gegrond** op de nieuwe schermen volgens de aangescherpte toon —
  ideeën-lege-staat ("sterrenveld dat wacht op jouw ster" -> "Wees de eerste — gooi je idee erin"),
  leden-lege-staten ("Geen ster op deze coördinaten" -> "Niets gevonden"), leden-hero ("levend
  netwerk / Elke ster" -> direct), ideeën/roadmap-intro's. Visuele kosmische identiteit blijft.
### Added
- **Roadmap geseed** met de gevraagde toekomst-features (status: overwegen): events met rollen
  (ik spreek / ik ben erbij / ik organiseer), forum met subgroepen + threads, direct messaging,
  notificaties, member dashboard.

## [0.9.2] - 2026-06-18
### Changed
- **Onboarding `/welkom` herschreven** tot een echte onboarding i.p.v. een auto-doorverwijspagina:
  geen auto-redirect meer (de maker klikt zelf "Aan de slag →"), de domein-woordgrap "Welkom in de
  wereld van AI", en eenvoudige, directe copy ("Laten we aan jouw stukje van die wereld werken")
  zonder zweverigheid. Kosmische visuele identiteit blijft.
- **Toon vastgelegd: in-app taal is eenvoudig, direct en to the point — niet zweverig/poëtisch.**
  Aangepast in `docs/STYLEGUIDE.md` (§3 microcopy + anti-patterns) en het ervaringsmandaat in
  `CLAUDE.md`: verbazen door de ervaring en de intelligentie, niet door bloemrijke woorden;
  geen auto-redirects vermomd als "ervaring".

## [0.9.1] - 2026-06-18
### Fixed
- **Profielbouwer: vervolgvraag "verdween" na het done-event** — de done-bubbel
  her-extraheerde de tekst uit `final` (de laatste pause_turn-iteratie), die na een
  web_fetch-loop leeg kan zijn -> lege "…"-bubbel. De `/stream`-generator accumuleert nu
  de gestreamde tekst-deltas en gebruikt die als fallback, zodat de reply zichtbaar blijft.

## [0.9.0] - 2026-06-18
### Added (Ervaring-laag E1-E4 + wacht-UX)
- **Feedback overal** (E1): altijd-bereikbare "✦ deel je gedachte"-affordance (htmx-paneel),
  opslag met paginacontext, optionele Claude-samenvatting (faalt gracieus), admin-overzicht.
- **Ideeënbus** (E2, `/ideeen`): indienen, stemmen (1 upvote/lid/idee, UNIQUE), status; admin
  modereren + promoten naar de roadmap.
- **Roadmap** (E3, `/roadmap`): levende, admin-curated roadmap (DB-backed), gevoed door ideeën.
- **Onboarding + gestylede e-mails** (E4): kosmische HTML-mails (magic-link + goedkeuring) achter
  de bestaande EmailSender; cinematische eerste-login die doorvloeit naar de profielbouw.
- **Wacht-UX** (W): gloeiend "AI-aan-het-werk"-paneel met live-redenering + constellatie i.p.v.
  statische "..."; additieve SSE-events, `delta`/`done` byte-identiek (AI-fixes intact).
- Migratie `0005_ervaring` (additief): `feedback`, `idea`, `idea_vote`, `roadmap_item`.
- _Nog NIET gedeployed — wacht op de profielbouw-vision-richting (zie gesprek)._

## [0.8.5] - 2026-06-18
### Fixed (AI-profielbouw — live-bugs, gediagnosticeerd op productie)
- **Profielbouwer hing ("..."): `web_fetch`-resultaten teruggespeeld met `citations`**
  gaven `400 Extra inputs are not permitted`. Nieuwe `_strip_citations()` verwijdert het
  veld uit `web_fetch_tool_result`/`web_search_tool_result`-blokken vóór elke API-call
  (stream-loop, pause_turn-replay, finalize). Pause-replay dumpt Pydantic-blokken naar dict.
- **`url_not_allowed` op links na een komma**: de URL-regex pakte de trailing komma mee
  (`theuws.com,`), die belandde in `allowed_domains` en matchte nooit → de meeste links
  werden geweigerd. `_member_domains` stript nu trailing leestekens uit de host. (Géén
  botbescherming/robots — bewezen via productie-diagnose: alle 5 sites halen nu op, 0 fouten.)
- **System-prompt forceert nu het ophalen van ELKE opgegeven link** en verbiedt het lui
  als "onbereikbaar" bestempelen zonder een echte `error_code`.

## [0.8.4] - 2026-06-18
### Added (Publieke ledenpagina + profielverrijking + SEO — L1-L4)
- Magische profielfoto-upload, prominentie-keuze (persoon↔projecten), kosmische publieke
  ledenpagina (`/leden`, constellatie), detailpagina's per persoon én project
  (`/projecten/{slug}`), SEO/linkwaarde (slugs + 301, OG/Twitter, JSON-LD, sitemap, robots).
  Migratie `0004_ledenpagina` (additief). Zie ook de review-fixes hieronder.
### Fixed
- **Prominentie zichtbaar op de detailpagina** (`cosmic.css`): `emphasis-person`
  schaalt nu de hero-foto (208px) + naam/headline zichtbaar op t.o.v. `balanced`,
  en `emphasis-projects` tempert de headline — de drie keuzes zijn op
  `/leden/{slug}` voelbaar verschillend (PRD L1 / styleguide-toetssteen). Op mobiel
  blijft person groter maar getemperd (148px).
- **AI-regenerate behoudt project-slugs + 301** (`ai_profile.py`): `_persist_draft`
  reconcilieert offerings nu op positie i.p.v. clear+recreate. Een gewijzigde
  projecttitel loopt via `offering_slug.rename_to` (schrijft slug-historie + houdt
  het 301-pad live); een ongewijzigde titel houdt exact dezelfde slug. Geen verlies
  van geïndexeerde `/projecten/{slug}`-URL's of linkwaarde meer.
- **301-redirect lekt niet langer het bestaan van besloten projecten**
  (`projects.py` + `offering_slug.py`): de historische-slug-301 past nu dezelfde
  `can_view`-poort toe als de directe tak (via nieuwe `redirect_offering`), zodat
  het statusverschil (301 vs 404) het bestaan/slug van een geschorst/besloten
  project niet meer prijsgeeft aan anonieme bezoekers.
- **Foto-upload-cap is nu echt 6 MB** (`photo.py`): de route parst de multipart
  expliciet met `max_part_size=max_upload_bytes`, zodat Starlette's impliciete
  1 MB-default een normale telefoonfoto (>1 MB) niet meer kapt met een rauwe
  framework-fout; te grote parts vallen in de vriendelijke NL-400.
- **Dubbel `style`-attribuut** (`members/index.html`, `profiles/view.html`,
  `projects/view.html`): de reveal-delay (`--d`) is samengevoegd in het bestaande
  `style`, zodat de gestaggerde entrance van lede + footer niet meer op 0ms valt.
- **Migratie/model-drift** (`0004_ledenpagina.py`): `profile.emphasis` is nu
  `VARCHAR(8)` (was 20), exact gelijk aan het model — geen `alembic check`-drift.

### Tests
- `tests/test_photo_route.py` (nieuw): HTTP-laag-dekking voor de multipart-grens —
  een ~2 MB foto slaagt, een >6 MB part geeft de vriendelijke 400.
- `tests/test_ai_profile_routes.py`: regenerate-met-titelwijziging behoudt de
  offering-rij + slug en levert een echte 301 op de oude `/projecten/{slug}`.

## [0.8.3] - 2026-06-18
### Docs
- **`docs/PRD-ledenpagina.md`** — PRD voor publieke ledenpagina (kosmische constellatie van leden),
  detailpagina's per persoon én project, profielfoto-upload (magisch, altijd), prominentie-keuze
  (persoon ↔ projecten), en SEO/linkwaarde (slugs, OG, JSON-LD, sitemap). Fasen L1–L4. APPROVAL PENDING.
- `docs/STYLEGUIDE.md`: linkwaarde/SEO toegevoegd als expliciet doel (§5).

## [0.8.2] - 2026-06-18
### Docs
- **Ervaringsmandaat** in `CLAUDE.md` (niet-onderhandelbaar: altijd/iedereen/overal verbazen;
  generieke/MVP-look = regressie; "superslim"-as; toetssteen per scherm).
- **`docs/STYLEGUIDE.md`** — "kosmische diepte" concreet: kleurtokens, Fraunces/JetBrains Mono/
  Spline Sans, motion (+ reduced-motion), nebula/gloed/grain/constellatie, microcopy, a11y,
  per-scherm-checklist + anti-patterns.
- **`docs/PRD-ervaring.md`** — PRD voor slimme interface + centrale pagina's: feedback overal,
  ideeënbus (stemmen), roadmap (admin-curated), cinematische onboarding. Fasen E1–E4. APPROVAL PENDING.

## [0.8.1] - 2026-06-18
### Security
- Stored XSS gedicht: `safe_url`-Jinja-filter (alleen `http`/`https`/relatief)
  toegepast op AI/pagina-geleverde `url`/`image_url`/`cover_image_url` in
  `_cosmic_link_card.html`, `_cosmic_project_card.html` en `view.html` — blokkeert
  `javascript:`/`data:`-schema's in `href`/`src` op het publieke profiel.
- DOM-XSS via de live SSE-stream gedicht: elke assistant-delta wordt server-side
  HTML-geëscaped (`markupsafe.escape`) vóór het `delta`-event, zodat de live-bubbel
  als tekst rendert (sluit het prompt-injection→XSS-pad en de markup-flash).
- AVG-scope afgedwongen: `web_fetch` wordt beperkt tot de door het lid geplakte
  domeinen (`allowed_domains`) en `web_search` vervalt zodra er links zijn; system-
  prompt herhaalt dat opgehaalde paginacontent gegevens zijn, geen instructies.

### Fixed
- AVG-retentie: `POST /profiel/ai/opnieuw` wist nu ook `ai_source_text` en de in de
  sessie gegenereerde `cover_image_url` (de knop beloofde dat al).
- Publiek profiel is zonder JS zichtbaar: `<noscript>`-vangnet forceert
  `[data-reveal]`-content zichtbaar (progressive enhancement i.p.v. JS-gate).
- A11y: streamende assistant-bubbel krijgt `aria-live="polite"`; typing-indicator
  krijgt `role="status"` + visueel-verborgen label.
- Opschoning: SSE-drain-protocol (sentinel + timeout) leeft nu uitsluitend in
  `_Channel.get`; de router-duplicatie (`_blocking_get`, dubbele `_DONE`-import,
  tweede `120.0`) is verwijderd.

## [0.8.0] - 2026-06-18
### Added (AI-native profielbouw — ROUTES+UI, F1-F3)
- Router-bodies in `app/routers/ai_profile.py`: `GET /profiel/ai/bouwen` (kosmische
  chat-bouwpagina), `POST /profiel/ai/bericht` (persist user-turn + SSE-container),
  `GET /profiel/ai/stream` (SSE: tekst-deltas + `done`-bubbel; sync SDK in threadpool,
  refusal-veilig), `POST /profiel/ai/maak-draft` (structured output → DRAFT zonder
  `visibility` te zetten), `POST /profiel/ai/cover` (F2, faalt gracieus),
  `POST /profiel/ai/draft/bewerken`, `POST /profiel/ai/publiceren` (delegeert naar de
  bestaande zichtbaarheidsflow; consent vereist voor public), `POST /profiel/ai/opnieuw`.
- `app/services/ai_conversation.py`: DB-conversatie-state (`load_messages` /
  `append_turn` / `clear_turns` / `has_turns`) + in-process SSE-`_Channel`.
- Kosmische identiteit: `app/static/cosmic.css` (tokens + nebula/gloed/sterren/grain,
  Fraunces + JetBrains Mono + Spline Sans, `prefers-reduced-motion`-veilig);
  `base.html` (fonts + cosmic.css + htmx-sse + "Bouw met AI"-nav).
- Herontworpen publieke profielpagina `profiles/view.html` (kosmische diepte; cover-hero,
  headline/bio/rollen/projects-met-beeld/seeking/tags; OG-tags alléén voor public;
  noindex + login-gating gerespecteerd) + partials (`_cosmic_bg`, `_cosmic_link_card`,
  `_cosmic_project_card`, `_cosmic_tags`).
- Bouwflow-templates (`ai/build.html`, `_chat_message`, `_message_sent`, `_draft_preview`,
  `_draft_card_link`, `_cover`, `_cosmic_canvas`).

## [0.7.0] - 2026-06-18
### Added (AI-native profielbouw — FOUNDATION, F1-F3)
- Datamodel (additief, breekt geen bestaande tabellen): `profile` krijgt `headline`,
  `cover_image_url`, `ai_enriched`, `ai_source_text`; `offering` krijgt `url`, `image_url`;
  nieuw `ProfileLink`-model (`profile_link`: rollen/affiliaties + builds met beeld) en
  `AiChatTurn`-model (`ai_chat_turn`: server-side conversatie-state). Migratie
  `0003_ai_profile` (strikt additief; up+down geverifieerd).
- Enum `ProfileLinkKind` (`native_enum=False` → VARCHAR + CHECK, SQLite/Postgres-pariteit).
- `ImageGenerator`-interface (`app/ai/`): `Protocol` + `FalImageGenerator` (fal.ai flux/schnell
  via httpx, faalt gracieus → `url=None`) + `NoopImageGenerator` (fallback) + factory
  `get_image_generator()` via settings; deps-injectie `image_generator()` (overridable in tests).
- Config: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-opus-4-8`), `FAL_KEY`,
  `AI_ENRICH_ENABLED`, `RATE_LIMIT_AI_ENRICH_PER_HOUR`, `AI_IMAGE_BACKEND`; `.env.example` bijgewerkt.
- `requirements.txt`: `anthropic==0.69.0`.
- Stubs voor de volgende build-fasen: `app/services/ai_profile.py` (PROFILE_SCHEMA,
  `DraftProfile` dataclass, `_to_draft`-guard, Anthropic twee-staps signatures) en
  `app/routers/ai_profile.py` (lege `APIRouter`, gewired in `app/main.py`); Pydantic-schemas
  in `app/schemas/ai_profile.py` (`ChatMessageForm`, `AcceptForm`, `DraftProfileOut`).

## [0.6.1] - 2026-06-18
### Docs
- `docs/PRD-ai-profiel.md`: PRD voor AI-native profielbouw — gesprek met Claude Opus 4.8
  (`web_fetch`/`web_search` + structured outputs) dat links ophaalt/verrijkt incl. echte beelden,
  plus fal.ai-cover. Datamodel, edge cases, fasering. APPROVAL PENDING.

## [0.6.0] - 2026-06-17
### Added
- `CloudflareEmailSender` (`app/email/cloudflare_sender.py`): productie-e-mail via de
  Cloudflare Email Service REST-API (`/accounts/{id}/email/sending/send`), achter dezelfde
  `EmailSender`-interface. Selecteerbaar via `EMAIL_BACKEND=cloudflare`.
- Config: `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` (token-permissie "Email Sending: Edit").
- Tests: factory-selectie + failure-surfacing (non-2xx + netwerkfout) voor de Cloudflare-backend.
### Notes
- Activatie wacht op: Email Service per-account aanzetten (beta) + verzenddomein onboarden
  (SPF/DKIM) + de "Email Sending: Edit"-scope op het CF-token. Tot dan blijft `console` actief.

## [0.5.0] - 2026-06-17
### Added
- Teaser/coming-soon-pagina (`teaser/`): self-contained "kosmische diepte"-landing —
  canvas-constellatie (driftende sterren die verbindingslijnen vormen), nebula-mesh,
  Fraunces + JetBrains Mono + Spline Sans, roterende maker-rollen, e-mailwachtlijst.
- Minimale teaser-service (FastAPI + SQLite): serveert de pagina, `/healthz`, en
  `/api/waitlist` (e-mailvalidatie, idempotent via UNIQUE).
- Docker-compose (teaser + cloudflared) voor de M4.
### Deployed
- **Live op https://dewereldvan.ai** — self-host op M4 achter een eigen Cloudflare Tunnel
  `dewereldvan-teaser` (los van `n8n-tunnel`), ingress + DNS (apex + www) via de CF API.
### Decided
- E-mail definitief via **Cloudflare Email Service** (Workers Paid actief) i.p.v. Resend —
  één vendor voor DNS + tunnel + e-mail, laagste op-last. Zie context/decisions.md.

## [0.4.0] - 2026-06-17
### Security
- CSRF-bescherming op alle state-changing requests (`app/csrf.py`): per-sessie
  token in de signed cookie, gevalideerd op POST/PUT/PATCH/DELETE via een
  pure-ASGI middleware. Token in verborgen veld (HTML-forms) en als
  `X-CSRF-Token`-header (htmx, globaal via `hx-headers` op `<body>`).
  SameSite=Lax blijft als defense-in-depth.
- Session-cookie krijgt de `Secure`-flag (`https_only=True`) +
  `ProxyHeadersMiddleware` zodat de app het https-schema van de Cloudflare-tunnel
  vertrouwt op de interne http-hop.
- Open registratie per-IP rate-limited (`rate_limit_register_per_hour`, default
  5) tegen e-mail-bombing / ongebreidelde pending-rij-groei; nieuwe kolom
  `member.registration_ip`. Idempotente herhalingen en de admin-bootstrap-mail
  worden niet geteld.
- Magic-link single-use is nu concurrency-veilig: consumptie via atomische
  `UPDATE ... WHERE used_at IS NULL`; een gelijktijdige tweede verify krijgt
  `used` i.p.v. een tweede sessie.
### Added
- Eerste-admin-bootstrap: een geconfigureerd `ADMIN_EMAILS`-adres registreert
  direct als `approved` + `admin` (met audit-rij), zodat een verse deployment
  niet vastloopt zonder approver.
- AVG: expliciete instemming bij publiek zetten. `Profile.consented_public_at`
  legt het moment van toestemming vast; `change_visibility()` weigert de
  publieke transitie zonder consent (`ConsentRequired`) en het edit-formulier
  heeft een verplichte toestemmings-checkbox.
### Fixed
- Geschorste/geweigerde leden worden gedelist: een publiek profiel van een
  niet-approved eigenaar is niet langer wereld-leesbaar of indexeerbaar
  (`can_view`/`is_noindex` poorten op eigenaar-status).
- Admin htmx approve/reject/suspend op een verdwenen lid retourneert nu een
  inline `<tr>`-fragment i.p.v. de volledige 404-pagina (correcte htmx-swap).
- `ConsoleEmailSender` lekte een file-handle per verzending (outbox.log nu via
  context-manager).
### Changed
- `_naive_utc` (3× gedupliceerd in services) geconsolideerd naar
  `app.security.naive_utc`.
- Profiel-offerings/needs toevoegen/verwijderen via relatie-collectie
  (idiomatisch SQLAlchemy 2.x) i.p.v. `db.refresh` + dubbele flush.
- Dode alias `require_approved` verwijderd (`require_member` was de enige
  gebruiker).

## [0.3.0] - 2026-06-17
### Added
- Fase 1 profielen-MVP (FEATURES): volledige flows op de Fase-0-fundering.
- Auth (`app/routers/auth.py`): open registratie (idempotent op dubbele e-mail),
  passwordless magic-link aanvraag/verificatie (eenmalig, gehasht, TTL),
  uitloggen. Admin-notificatie-e-mail bij nieuwe aanmelding.
- Profielen (`app/routers/profiles.py`): profiel bewerken (bio, "wat ik maak",
  "waar ik naar zoek", tags), completeness-indicator, zichtbaarheid per profiel
  (alleen-leden default / openbaar), publieke slug-pagina (indexeerbaar) vs.
  besloten (login-gated + `noindex`). htmx voor offering/need toevoegen+
  verwijderen en de zichtbaarheid-toggle.
- Admin (`app/routers/admin.py`): goedkeuringsqueue met één-klik goedkeuren/
  weigeren/schorsen (htmx row-swap) + audit_log.
- Services (`app/services/`): registration (idempotent + pending-expiry purge),
  magic_link (issue/verify, single-use, expiry, rate-limit), approval
  (state-machine + audit), profile_service (upsert, offerings/needs/tags,
  completeness-scoring), visibility (wijziging + audit + read-enforcement).
- Schemas (`app/schemas/`): Pydantic v2 forms voor registratie, login en profiel
  (e-mailvalidatie via regex — geen extra dependency).
### Fixed
- Tijdzone-mismatch tussen tz-aware `utcnow()` en de tz-naive timestamp-kolommen:
  service-laag normaliseert naar naive-UTC vóór opslag/vergelijking (zou ook op
  Postgres `TIMESTAMP WITHOUT TIME ZONE` falen).
### Edge cases afgedekt (PRD §4)
- Dubbele registratie idempotent; geen account-enumeratie bij login.
- Verlopen/hergebruikte/ongeldige magic-link → nette her-aanvraag (geen silent fail).
- E-mailverzending mislukt → zichtbare foutstatus (502), nooit stil.
- Zichtbaarheid openbaar→besloten → direct delisten + `noindex` op de read-path.
- Pending-account-expiry + `purge_expired_pending`; rate-limit op magic-link.
- AVG: audit_log bij goedkeuringen/weigeringen/schorsingen en zichtbaarheidswijziging.

## [0.2.0] - 2026-06-17
### Added
- Fase 0 fundering: FastAPI app-factory met SessionMiddleware (signed cookies),
  Jinja2-templates, static, `/healthz` (app + DB-ping), landing + 404/500 pagina's.
- SQLAlchemy 2.x getypeerde modellen (Mapped/mapped_column): member, magic_link_token,
  profile, tag + profile_tag (M2M), offering, need, audit_log. Enums als VARCHAR+CHECK
  (`native_enum=False`) voor identieke schema's op Postgres en SQLite.
- `app/security.py`: magic-link tokengeneratie/hashing/verificatie (raw token nooit
  opgeslagen) + slug-helpers.
- E-mail-abstractie (`app/email/`): EmailSender Protocol, ConsoleEmailSender (dev-outbox),
  ResendEmailSender (prod), backend-selectie via `EMAIL_BACKEND`.
- Config via pydantic-settings (`app/config.py`) + `.env.example`.
- Gedeelde deps (`app/deps.py`): current_member, require_member/require_approved,
  require_admin, email_sender.
- Lege router-stubs (auth/profiles/admin) gekoppeld in `main.py` voor de FEATURES-fase.
- Alembic baseline-migratie `0001_initial_fase1` met alle Fase-1 tabellen.
- Docker: Dockerfile (python:3.12-slim), docker-compose (web + postgres + cloudflared,
  healthchecks, restart: unless-stopped, pgdata-volume), `.dockerignore`.
- `requirements.txt` (gepinde 2026-versies), `pyproject.toml` (pytest + ruff).

## [0.1.0] - 2026-06-17
### Added
- Projectinitialisatie: git op `main`, CLAUDE.md (Groot scope), context-documentatie.
- Architectuur, beslissingen en tech-stack vastgelegd.
- PRD/roadmap (`docs/PRD.md`) met fasering Fase 0–5 en edge cases — APPROVAL PENDING.
- Kernbeslissingen: visie (directory+matchmaking+community+showcase), open registratie +
  goedkeuring + magic-link, zichtbaarheid per profiel, self-host M4 + Cloudflare Tunnel,
  stack FastAPI + SQLAlchemy + Jinja2/htmx + Postgres.
