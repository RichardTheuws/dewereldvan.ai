# dewereldvan.ai

> **De wereld van makers in het AI-tijdperk.**
> Een groeiende constellatie van mensen die intensief met AI werken — van beleidsmakers en
> trainers tot programmeurs, beeld- en geluidsmakers en gamebouwers.

**Status:** 🌱 in aanbouw · **Teaser live:** **[dewereldvan.ai](https://dewereldvan.ai)** · **Versie:** zie [`VERSION`](VERSION)

---

## Wat is dit?

dewereldvan.ai wordt een platform waar de leden van onze community een **profiel** aanmaken:
wie ze zijn, **wat ze maken**, en **waar ze naar op zoek zijn**. Vanuit dat fundament groeit het
naar een **ledengids**, **matchmaking** (vraag & aanbod koppelen), **community** en een
**publieke showcase** van het werk van leden.

Het project is bewust **open** opgezet: leden mogen meebouwen aan de plek die van henzelf is.
Deze README legt uit wáár je aan kunt meewerken en **hoe**.

## Waar staan we nu?

| | |
|---|---|
| ✅ **Teaser live** | Een coming-soon-pagina met e-mailwachtlijst op [dewereldvan.ai](https://dewereldvan.ai) |
| ✅ **Fase 0 — Fundering** | FastAPI-app, datamodel, migraties, Docker, e-mail-abstractie, CSRF, tests groen |
| ✅ **Fase 1 — Profielen-MVP** | Registratie → goedkeuring → magic-link-login → profiel bewerken → zichtbaarheid (code af, deploy volgt) |
| 🔜 **Fase 2 — Directory** | Doorzoekbare ledengids, publieke profielpagina's, AVG-export/-delete |
| 🔜 **Fase 3 — Matchmaking** | "zoekt" ↔ "maakt" koppelen + tag-suggesties |
| 🔜 **Fase 4 — Community** | Posts/updates + reacties + lichte moderatie |
| 🔜 **Fase 5 — Showcase** | Etalage naar buiten, SEO |

De volledige roadmap met edge cases staat in **[`docs/PRD.md`](docs/PRD.md)**.

## Hoe het werkt (kort)

- **Toegang:** open registratie → een beheerder keurt nieuwe leden goed → daarna log je
  **zonder wachtwoord** in via een magic-link per e-mail.
- **Zichtbaarheid:** je kiest **per profiel** of het publiek is of alleen voor leden. Default is
  besloten; publieke profielen krijgen een eigen URL en zijn vindbaar.
- **Privacy/AVG:** minimale dataverzameling, expliciete keuze bij publiek zetten, en (vanaf
  Fase 2) self-service export + verwijderen.

## Tech stack

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy 2.x (typed) · Alembic
- **Frontend:** server-rendered Jinja2 + **htmx** + Tailwind — *geen* JS-buildpipeline (lage onderhoudslast)
- **Database:** PostgreSQL
- **Auth:** passwordless magic-link (signed tokens) + server-side sessies · CSRF-bescherming
- **E-mail:** abstractie met dev-console-backend + Cloudflare Email Service in productie
- **Infra:** Docker Compose, self-hosted achter een Cloudflare Tunnel

Architectuur in detail: **[`context/architecture.md`](context/architecture.md)** ·
keuzes + afwegingen: **[`context/decisions.md`](context/decisions.md)**.

## Repo-structuur

```
app/            FastAPI-applicatie (routers, models, services, templates, deps)
  models/       SQLAlchemy-modellen (member, profile, tag, offering, need, …)
  routers/      auth · profiles · admin
  services/     registratie · magic-link · goedkeuring · profiel · zichtbaarheid
  templates/    Jinja2 + htmx (base + auth/ profiles/ admin/)
alembic/        database-migraties
tests/          pytest (draait op SQLite, geen Postgres nodig)
teaser/         de live coming-soon-pagina (los, transitioneel)
context/        architecture · decisions · techstack · status
docs/           PRD / roadmap
```

## Lokaal draaien

```bash
# 1. Virtuele omgeving + dependencies
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Config
cp .env.example .env
#   - zet SECRET_KEY   (genereer: openssl rand -hex 32)
#   - EMAIL_BACKEND=console  → magic-links worden naar data/outbox/ geschreven (klikbaar in dev)

# 3. Database (Postgres) + migraties
export DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/dewereldvan
alembic upgrade head

# 4. Start
uvicorn app.main:app --reload      # → http://localhost:8000

# 5. Tests (geen Postgres nodig)
pytest         # SQLite in-memory
ruff check app
```

Of volledig in Docker: `docker compose up -d --build` (zie [`CLAUDE.md`](CLAUDE.md) voor details).

## 🙌 Waar kun je aan meewerken?

Alle niveaus welkom — van één regel copy tot een hele feature. Pak iets dat bij je past:

| Gebied | Wat | Goed als je houdt van |
|--------|-----|------------------------|
| 🎨 **Frontend / UI** | Profielpagina's, directory-filters, polish, micro-interacties | htmx · Jinja2 · Tailwind · CSS |
| ⚙️ **Backend** | Matchmaking-logica, community-features, API, performance | Python · FastAPI · SQLAlchemy |
| 🧭 **Design / UX** | Visuele taal, componenten, toegankelijkheid (a11y) | design · UX · accessibility |
| 🔗 **Matchmaking (Fase 3)** | "zoekt ↔ maakt" koppelen, tag-suggesties | data · algoritmes |
| 💬 **Community (Fase 4)** | Posts, reacties, lichte moderatie | product · sociale features |
| ✍️ **Content & copy** | Teksten, onboarding, microcopy — in het Nederlands | taal · communicatie |
| 🧪 **Testing / QA** | pytest-coverage, edge cases, randgevallen | kwaliteit · test |
| 🛠️ **Infra / DevOps** | Docker, Cloudflare, backups, monitoring | ops · deployment |
| 🔐 **Privacy / AVG** | Data-minimalisatie, export/verwijderen, consent | privacy · compliance |

Geen idee waar te beginnen? Open een **issue** met je vraag of idee, of reageer op een issue
met het label `good first issue`.

## Hoe bij te dragen

1. **Lees je in:** [`docs/PRD.md`](docs/PRD.md) (de roadmap), [`context/`](context/) (architectuur + keuzes).
2. **Stem af:** open een **issue** voor wat je wilt oppakken (voorkomt dubbel werk) of claim een bestaande.
3. **Branch** vanaf `main`.
4. **Conventional commits:** `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, …
5. **Kwaliteit:** `pytest` groen en `ruff check app` schoon vóór je een PR opent. Schrijf tests
   bij nieuwe functionaliteit.
6. **Open een Pull Request** met een korte beschrijving van *wat* en *waarom*. Voeg screenshots
   toe bij UI-werk.

Principes die we hooghouden: **lage operationele last** (het moet unattended kunnen draaien),
**privacy by design**, en **geen onnodige complexiteit** — kies de eenvoudigste oplossing die werkt.

## Documentatie

- 📋 [`docs/PRD.md`](docs/PRD.md) — product requirements + roadmap + edge cases
- 🏛️ [`context/architecture.md`](context/architecture.md) — systeem, datamodel, fasering
- 🧠 [`context/decisions.md`](context/decisions.md) — beslissingen mét afgewezen alternatieven
- 📦 [`context/techstack.md`](context/techstack.md) — stack + constraints
- 🚦 [`context/status.md`](context/status.md) — huidige focus + open taken

## Licentie

Nog te bepalen — open gerust een issue als je hierover wilt meedenken. Tot die tijd: vraag het
even voordat je code hergebruikt buiten dit project.

## Community

Dit platform is van en voor de makers in de community. Vragen, ideeën, of meebouwen?
Open een issue of zet je op de wachtlijst via [dewereldvan.ai](https://dewereldvan.ai).
