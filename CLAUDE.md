# dewereldvan.ai

## Overzicht
Platform voor de leden van een WhatsApp-groep om een profiel aan te maken: wie ze zijn,
wat ze maken, en waar ze naar op zoek zijn. Het MVP is profielen + ledengids; de visie is
breder — directory, matchmaking (vraag/aanbod), community en een publieke showcase van het
werk van leden. Domein `dewereldvan.ai` staat op Cloudflare; self-hosted op de Mac mini M4
achter een Cloudflare Tunnel.

## ✨ Ervaringsmandaat (NIET ONDERHANDELBAAR)
dewereldvan.ai is een open, gastvrije community voor iedereen in NL/BE die met AI bouwt, traint,
ontwerpt, onderzoekt of er beleid over maakt — van wie net begint tot wie er dagelijks mee werkt.
**Elke pixel en elke interactie moet hen verwelkomen én verbazen.** Dit is geen nice-to-have maar
de kern van het product. We positioneren niemand "hoog" of exclusief: de toon is overal open en
uitnodigend, nooit elitair — en juist daarbinnen verrast de ervaring.

- **ALTIJD, IEDEREEN, OVERAL verbazen.** Geen enkele pagina, flow of e-mail mag "een formuliertje
  op een pagina" zijn. Onboarding, profielbouw, feedback, roadmap, ideeënbus — álles krijgt de
  next-level, kosmische behandeling. Een generieke/MVP-look is een **regressie**, geen acceptabel
  tussenstadium.
- **Bouw nooit een kale interactie.** Vraag je bij elk scherm af: "voelt dit warm én verrassend —
  voor wie net begint én voor wie dagelijks met AI bouwt?" Zo nee → niet af.
- **De stijl is gedefinieerd, niet vrij in te vullen.** Volg **[docs/STYLEGUIDE.md](docs/STYLEGUIDE.md)**
  ("kosmische diepte") tot in de details: typografie, kleur, motion, compositie, microcopy. Hergebruik
  `app/static/cosmic.css` en de teaser-identiteit; introduceer geen tweede look.
- **Slim, niet alleen mooi.** De interface helpt actief: feedback geven kan overal, suggesties worden
  aangeboden, AI assisteert. "Superslim" is onderdeel van het ontwerp, geen feature-vinkje.
- **Verbaas door de ERVARING en de INTELLIGENTIE, niet door zweverige taal.** De visuele identiteit is
  kosmisch en verfijnd; de **woorden zijn eenvoudig, direct en to the point** — in-app schrijven we
  gewone, heldere taal (geen "je ster is verschenen", wél "Welkom"). Geen auto-redirects vermomd als
  "ervaring": een onboarding is een moment waar de maker zélf doorklikt.
- Bij twijfel: kies de meer verrassende, meer verfijnde optie — maar altijd helder en bruikbaar.

## Context
Dit project gebruikt uitgebreide context-documentatie:
- [Status & taken](context/status.md)
- [Architectuur](context/architecture.md)
- [Beslissingen](context/decisions.md)
- [Tech Stack](context/techstack.md)
- [**Styleguide & ervaringsrichtlijnen**](docs/STYLEGUIDE.md) — "kosmische diepte", verplicht voor elk scherm
- [PRD / Roadmap](docs/PRD.md) · [PRD AI-profielbouw](docs/PRD-ai-profiel.md)

## Kernbeslissingen (zie context/decisions.md voor onderbouwing)
- **Visie**: directory + matchmaking + community + showcase — datamodel nu holistisch, bouw gefaseerd.
- **Toegang**: open registratie → admin-goedkeuring (lichtgewicht queue) → passwordless magic-link login.
- **Zichtbaarheid**: per profiel instelbaar, default besloten (alleen-leden).
- **Hosting**: self-host op M4 Docker, Cloudflare ervóór (DNS + Tunnel, geen open poorten).

## Tech Stack (samengevat)
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2.x + Alembic
- **DB**: PostgreSQL (Docker)
- **Frontend**: server-rendered Jinja2 + htmx + Tailwind (geen JS-buildpipeline → lage op-last)
- **Auth**: passwordless magic-link (signed tokens), server-side sessions
- **Infra**: Docker Compose, Cloudflare Tunnel (`cloudflared`), transactionele e-mail

## Quick Start (Fase 0 — fundering staat)
```bash
cp .env.example .env          # vul SECRET_KEY (openssl rand -hex 32) en TUNNEL_TOKEN
docker compose up -d --build  # web + postgres + cloudflared
# migraties draaien automatisch bij start (CMD: alembic upgrade head)
curl -s http://localhost:8000/healthz   # → {"status":"ok"} (binnen het compose-netwerk)
```

### Lokaal ontwikkelen zonder Docker
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # zet SECRET_KEY; EMAIL_BACKEND=console schrijft naar data/outbox/
export DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/dewereldvan
alembic upgrade head
uvicorn app.main:app --reload
pytest                        # SQLite in-memory, geen Postgres nodig
```

E-mail in dev (`EMAIL_BACKEND=console`) wordt gelogd én naar `data/outbox/` geschreven
(per bericht een `.txt` + een gecombineerde `outbox.log`) zodat magic-links klikbaar zijn.

## Deployment
Self-hosted op `server-mini` (M4) via Docker Compose, geëxposeerd met Cloudflare Tunnel.
Geen poortforwarding op de router. Details in context/architecture.md.

## Werkwijze
Volgt de globale workflow (~/.claude/CLAUDE.md): SemVer + CHANGELOG bij elke wijziging,
PRD-first voor nieuwe features, conventional commits op `main`, tests in dezelfde sessie.

**Source of truth**: `context/status.md` (waar staan we) en `context/decisions.md` (waarom) worden
**samen met elke `VERSION`/`CHANGELOG`-bump** bijgewerkt — anders drijven ze weg en misleiden ze.
`context/architecture.md` bijwerken bij structurele wijzigingen (nieuwe router/model/integratie).
Begin een sessie door `context/status.md` te lezen; dat is de canonieke toestand.
