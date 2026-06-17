# dewereldvan.ai

## Overzicht
Platform voor de leden van een WhatsApp-groep om een profiel aan te maken: wie ze zijn,
wat ze maken, en waar ze naar op zoek zijn. Het MVP is profielen + ledengids; de visie is
breder — directory, matchmaking (vraag/aanbod), community en een publieke showcase van het
werk van leden. Domein `dewereldvan.ai` staat op Cloudflare; self-hosted op de Mac mini M4
achter een Cloudflare Tunnel.

## Context
Dit project gebruikt uitgebreide context-documentatie:
- [Status & taken](context/status.md)
- [Architectuur](context/architecture.md)
- [Beslissingen](context/decisions.md)
- [Tech Stack](context/techstack.md)
- [PRD / Roadmap](docs/PRD.md) — **APPROVAL PENDING** (Fase 1 start ná akkoord)

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
