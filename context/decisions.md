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
