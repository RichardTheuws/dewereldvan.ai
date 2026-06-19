# Changelog

Alle noemenswaardige wijzigingen aan dit project worden hier vastgelegd.
Volgt [Keep a Changelog](https://keepachangelog.com/) en [SemVer](https://semver.org/).

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
