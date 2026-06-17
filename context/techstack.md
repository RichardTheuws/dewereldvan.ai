# Tech Stack

## Talen & Frameworks
| Tech | Versie | Doel |
|------|--------|------|
| Python | 3.12 | Applicatietaal |
| FastAPI | latest 2026 | Web framework (routes, async) |
| SQLAlchemy | 2.x | ORM |
| Alembic | latest | DB-migraties |
| PostgreSQL | 16 | Database |
| Jinja2 | latest | Server-side templating |
| htmx | latest | Interactiviteit zonder JS-build |
| Tailwind CSS | latest (CLI/CDN) | Styling |
| cloudflared | latest | Cloudflare Tunnel |

## Belangrijkste dependencies (verwacht)
- `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `psycopg[binary]`
- `jinja2`, `python-multipart` (forms), `itsdangerous` (signed magic-link tokens)
- `pydantic-settings` (config via env), `passlib` n.v.t. (geen wachtwoorden)
- e-mail-SDK afhankelijk van providerkeuze (OPEN)

## Development Setup
```bash
# (komt in Fase 0)
docker compose up -d            # web + postgres + cloudflared
docker compose exec web alembic upgrade head
# tests
docker compose exec web pytest
```

## Constraints
- **Geen JS-buildpipeline** — alles server-rendered + htmx (lage op-last).
- **Unattended** — restart-policy, healthcheck, nightly backup.
- **AVG/GDPR** — EU-data; data-export + verwijderrecht vanaf Fase 2; minimale dataverzameling.
- **Self-host op M4** — past binnen bestaande Docker-stack; Cloudflare Tunnel i.p.v. open poorten.
