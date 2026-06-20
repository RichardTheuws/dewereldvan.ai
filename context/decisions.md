# Architectuur Beslissingen

## Format
Elke beslissing bevat: **Context** (waarom kiezen), **Beslissing** (wat), **Alternatieven**
(afgewezen + reden), **Gevolgen** (impact).

---

## [2026-06-17] Visie: alle vier richtingen, datamodel holistisch

**Context**: MVP = profielen, maar "moet veel meer worden". Datamodel-keuze nu bepaalt of
uitbreiding later herbouw vereist.

**Beslissing**: Richting = directory + matchmaking + community + publieke showcase. Datamodel
nu holistisch ontworpen (member/profile/tag/offering/need/match/post/comment), bouw gefaseerd.

**Alternatieven**:
- Alleen MVP-datamodel nu, later uitbreiden: afgewezen — dwingt dure migratie/herbouw af.

**Gevolgen**: Iets meer ontwerpwerk vooraf; daarna kan elke fase additief bovenop hetzelfde model.

---

## [2026-06-17] Toegang: open registratie + admin-goedkeuring + magic-link

**Context**: Richard wil controle over wie binnenkomt, maar lage doorlopende op-last (kerneis).

**Beslissing**: Open registratieformulier → status `pending` → lichtgewicht admin-queue (één
klik goedkeuren) → daarna passwordless **magic-link** login. Goedkeuring is eenmalig per lid;
dagelijks inloggen vergt geen handwerk van Richard.

**Alternatieven**:
- Uitnodigingslink: afgewezen — zwakke identiteit, geen controle op wie binnenkomt.
- WhatsApp-OTP: afgewezen — externe SMS/WhatsApp-API, kosten per bericht, extra leverancier.
- Wachtwoorden: afgewezen — beheerlast (reset-flows, hashing-policy) zonder meerwaarde hier.

**Gevolgen**: Eénmalige handmatige goedkeuring per nieuw lid. Vereist transactionele e-mail.

---

## [2026-06-17] Zichtbaarheid: per profiel, default besloten

**Context**: "De wereld van" suggereert publiek, maar niet elk lid wil openbaar zijn.

**Beslissing**: Elk lid kiest per profiel: publiek of alleen-leden. Default = alleen-leden
(privacy-veilig). Publieke profielen krijgen openbare URL + indexeerbaar; besloten = `noindex`.

**Alternatieven**:
- Alles besloten: afgewezen — blokkeert de showcase-richting.
- Alles publiek: afgewezen — privacybezwaar, AVG-risico bij niet-instemmende leden.

**Gevolgen**: Visibility-veld vanaf Fase 1 in datamodel; directory en showcase respecteren het.

---

## [2026-06-17] Hosting: self-host M4 Docker + Cloudflare Tunnel

**Context**: Domein op Cloudflare. Kerneis: laag onderhoud, unattended. Richard draait al een
Docker-productiestack op de M4 (server-mini).

**Beslissing**: Self-host op M4 via Docker Compose, geëxposeerd met **Cloudflare Tunnel**
(`cloudflared`) — geen poortforwarding op de router. Cloudflare doet DNS, TLS en WAF.

**Alternatieven**:
- Cloudflare-native (Pages/Workers/D1): afgewezen — Richard koos expliciet self-host (controle,
  past in bestaande stack). [Was mijn initiële aanbeveling op grond van near-zero ops.]
- Vercel + Supabase: afgewezen — tweede leverancier, kosten lopen op bij groei.

**Gevolgen**: Backups/updates/monitoring liggen bij ons; sluit aan op bestaande M1-backup- en
health-routines. Cloudflare Tunnel vermijdt het grootste self-host-risico (open poorten).

---

## [2026-06-17] Stack: FastAPI + SQLAlchemy + Jinja2/htmx + Postgres

**Context**: Lage op-last, unattended, Richards sterke punt (Python/SQLAlchemy/Docker).

**Beslissing**: FastAPI + SQLAlchemy 2.x + Alembic, Postgres, server-rendered Jinja2 + htmx +
Tailwind. Geen losse SPA/JS-buildpipeline.

**Alternatieven**:
- Next.js/React-SPA: afgewezen — node-build/runtime-onderhoud, tegen lage-op-last-eis.
- Django: afgewezen — zwaarder; FastAPI+SQLAlchemy sluit beter aan op bestaande skills.

**Gevolgen**: Eén Python-service, geen frontend-build. htmx dekt matchmaking/community-interactie
incrementeel.

---

## [2026-06-17] Transactionele e-mail via Cloudflare Email Service

**Context**: Magic-link + goedkeurings-notificaties vereisen betrouwbare e-mailbezorging.
Domein staat op Cloudflare; kerneis is laagste op-last + één vendor waar mogelijk.

**Beslissing**: **Cloudflare Email Service** (public beta sinds apr 2026) via de HTTPS REST-API
(`POST /accounts/{id}/email/sending/send`), aanroepbaar vanaf de FastAPI-app op de M4 — geen
Workers-code nodig. Workers Paid-plan staat aan ($5/mnd, 3.000 mails inbegrepen). SPF/DKIM
worden automatisch op het domein gezet.

**Alternatieven**:
- Resend (€0 free tier): afgewezen — tweede vendor + tweede secret/dashboard voor marginale
  besparing; tegen de "één-vendor, lage op-last"-eis. (Adapter blijft in code als fallback.)
- Eigen SMTP-relay: afgewezen — deliverability + onderhoud zelf dragen.

**Gevolgen**: E-mail loopt via dezelfde API-token-infra als DNS + tunnel. Email-Sending-scope
op het token moet nog rond (zone werkt, sending-endpoint gaf nog 10001) + domein onboarden —
af te ronden bij het aansluiten van Fase 1. Dev gebruikt de console-outbox.

---

## [2026-06-17] Teaser live op M4 achter eigen Cloudflare Tunnel

**Context**: Community vast warm maken vóór het platform af is, zonder op de M4-deploy van de
volledige app te wachten.

**Beslissing**: Losse, minimale teaser-service (`teaser/`, FastAPI + SQLite-wachtlijst) op de
M4, geëxposeerd via een **eigen** tunnel `dewereldvan-teaser` (níét de bestaande `n8n-tunnel`),
DNS (apex + www) via de Cloudflare API. Live op https://dewereldvan.ai.

**Alternatieven**:
- Cloudflare Pages: afgewezen — token mist Pages/D1-scopes + tweede stack; tunnel hergebruikt
  de scopes die er al zijn.
- Wachten op volledige app-deploy: afgewezen — vertraagt het warmmaken nodeloos.

**Gevolgen**: Throwaway/transitioneel. Bij go-live van het platform neemt de volledige app de
tunnel-ingress over en migreren we de wachtlijst-adressen naar de `member`-tabel.

---

## [2026-06-20] Discovery: footprint-engine, gefaseerd, met confirm-poort

**Context**: leden moeten hun online werk/vermeldingen makkelijk op hun profiel krijgen. De markt
faalt op disambiguatie (naamgenoten). Engine wordt later hergebruikt door de Scout.

**Beslissing**: één `footprint_service` (zoek → entity-resolution → classificeer) met twee
consumenten (Discovery nu, Scout later). Gebouwd in fasen: **1a** = live-streamende ontdekking +
kandidaten; **1b** = crystalliseer/bevestig-laag. Hoge confidence (**≥90**, `HIGH_CONFIDENCE`)
crystalliseert auto mét undo; twijfel → 1-klik "klopt dit?"-bevestigrij. Crystalliseren is
idempotent op URL (geen duplicaten). KILL-conditie: zakt de precisie, val terug op
confirm-everything (engine blijft, auto-magie eruit).

**Alternatieven**:
- Alles altijd handmatig bevestigen: afgewezen — Richard koos auto-≥90 (PRD-default) voor de wow.
- Links dumpen zonder entity-resolution: afgewezen — disambiguatie ÍS de moat.

**Gevolgen**: false-positive-risico afgedekt door drempel + undo + idempotentie. PRD: `docs/PRD-discovery.md`.

## [2026-06-20] Discovery draait als achtergrond-job (niet inline)

**Context**: de ontdekking duurt vaak >5 min; de inline-SSE sneuvelde op de 2-min-cap
(`CHANNEL_TIMEOUT_SEC`) en bewaarde niets → terugkeren onmogelijk.

**Beslissing**: ontkoppel van het browservenster. Achtergrond-thread (`discovery_job_service`,
eigen sessie) draait de engine en persisteert naar **`DiscoveryRun`** (migr. 0019). Live-view
*tailt* de run over SSE met `Last-Event-ID`-hervatting; wie wegklikt verliest niets (terugkeer-view +
in-app chip). Webhook/2-min-cap raakt de job niet meer.

**Alternatieven**:
- Timeout ophogen: afgewezen — houdt iemand minuten op een breekbare tab.
- htmx-polling i.p.v. SSE-tail: afgewezen — SSE-tail over gepersisteerde staat hergebruikt de
  bestaande view en herstelt prima via Last-Event-ID.
- Progressive render (engine-fasering): uitgesteld — lost >5min niet op; persist maakt 't later goedkoop.

**Gevolgen**: foundation die de Scout (Fase 2) deelt. PRD: `docs/PRD-discovery.md`.

## [2026-06-20] Geen e-mail meer (behalve magic-link) → lid-gekozen notificatiekanaal

**Context**: e-mail past niet bij dit AI-native publiek; notificaties horen waar de aandacht al is.
Sluit aan op de Scout-PRD-pivot ("pull-only, geen e-mail, geen push").

**Beslissing**: e-mail blijft **alléén** voor de magic-link. Alle overige seintjes via een
**lid-gekozen kanaal**. AUGMENT, geen tweede systeem: in-app blijft de state-derived pull-chip;
een `notify()`-dispatcher voegt **push** toe naar het voorkeurskanaal. Default = in-app.
Discovery-klaar én matchmaking-intro lopen nu via `notify()` (e-mail verwijderd). Modellen
`member_channel` + `notification_pref` (migr. 0020); uitbreidbaar (nieuw kanaal = een Notifier erbij).

**Alternatieven**:
- E-mail houden voor intro's (1-op-1, tijdkritisch): afgewezen — Richard koos "álles via voorkeur-kanaal".
- Notificatie-inbox bouwen: afgewezen — de pull-chips dekken in-app al (lage op-last).

**Gevolgen**: een lid met default in-app dat de app niet opent mist realtime — Telegram is dé
push-route (bewuste trade-off). PRD: `docs/PRD-notificaties.md` · memory `dewereldvan-notificaties`.

## [2026-06-20] Telegram als eerste push-kanaal (deep-link + webhook)

**Context**: een echt push-kanaal naast in-app, met de laagste op-last.

**Beslissing**: bot **@dewereldvanaibot**. Koppelen via deep-link `t.me/<bot>?start=<token>`;
de bot-**webhook** (`POST /telegram/webhook`, secret-token-header, CSRF-exempt) koppelt de chat_id.
Eigen avatar via `setMyProfilePhoto` (Bot API 9.4). Rich content: HTML + inline-knop (robuust;
`sendRichMessage` van 10.1 bewust nog niet gebruikt). Gegate op `TELEGRAM_BOT_TOKEN` → activeert via env.

**Alternatieven**:
- Long-poll worker i.p.v. webhook: afgewezen — we hebben al een tunnel (webhook = lager op-last).

**Gevolgen**: creds in M4-`.env` (niet in git); webhook registreert zichzelf bij startup. Token
ooit roteren vóór publieke launch. Memory `dewereldvan-notificaties`.

## [2026-06-20] Discovery-verdieping: gerichte media-pass (append, media-first)

**Context**: de brede ontdekking vindt vooral eigen werk; media ÓVER een persoon
(interviews/artikelen) is een andere zoekintent. Natuurlijk agent-moment om dieper te graven.

**Beslissing**: een **focus-parameter** op de engine (`discover(..., focus="media")`) + een
opt-in-aanbod ("kom je weleens in het nieuws?"). De media-pass **append**t op de bestaande
`DiscoveryRun` (gededupeerd op URL) i.p.v. een aparte run/modus — geen schema-wijziging. Media
crystalliseert naar nieuws-`Post` (bestaand). **Media-first**; events als eigen focus uitgesteld.

**Alternatieven**:
- Aparte run per modus (`mode`-kolom + unique (member, mode)): afgewezen — append houdt schema +
  tail/resultaat/chip ongewijzigd; re-run dedupt.
- Alles in één brede pass: afgewezen — media-intent verdrinkt; opt-in spaart kosten/latency.
- Events nu meenemen: uitgesteld — eigen crystallisatie-doel (agenda) + eigen aanbod-copy.

**Gevolgen**: precisie-risico (naamgenoten in het nieuws) afgedekt door ankers + drempel + bevestigrij;
KILL de media-pass bij lage precisie (brede pass blijft). PRD: `docs/PRD-discovery-verdieping.md`.

## [2026-06-20] Affordances zijn progress-bewust (geen reeds-gebruikte verse knop)

**Context** (Richard): een ontdek-CTA bleef "Zal ik je opzoeken?" tonen ná de ontdekking, en het
media-aanbod bleef "zoek media" ook nadat die pass liep. Principe: de interface moet begrijpen wat
al gebruikt is en de vervolgstap aanpassen — geen dode/verse affordances laten staan.

**Beslissing**: stateful maken via `DiscoveryRun.passes` (voltooide focus-passes). CTA's en aanbiedingen
lezen die staat en passen zich aan (opzoeken→bekijken; "zoek media"→"al gezocht"). Dit is een **algemeen
ontwerpprincipe** voor de hele app, niet alleen Discovery: bied geen actie aan die al verbruikt is zonder
dat te tonen.

**Alternatieven**:
- Statische affordances + uitleg-tekst: afgewezen — misleidt (verse knop op verbruikte actie).
- Afleiden uit findings-types i.p.v. expliciet bijhouden: afgewezen — onbetrouwbaar (een 0-resultaat-pass
  laat geen spoor); expliciet `passes` bijhouden is eerlijk.

**Gevolgen**: nieuwe meertraps-flows houden hun voortgang bij en sturen de UI. PRD: `docs/PRD-discovery-verdieping.md`.
