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

## [OPEN] Transactionele e-mailprovider

**Context**: Magic-link + goedkeurings-notificaties vereisen betrouwbare e-mailbezorging.
**Status**: nog te beslissen vóór Fase 1. Kandidaten: Resend, Postmark, of eigen SMTP-relay.
Beslis op deliverability + kosten + AVG (EU-verwerking). Richards veto/voorkeur gewenst.
