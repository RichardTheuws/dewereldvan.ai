# Architectuur

## Systeem Overzicht
Eén self-hosted webapplicatie (server-rendered) achter een Cloudflare Tunnel. Geen aparte
SPA/JS-buildpipeline — interactiviteit via htmx. Dit houdt de operationele last laag en laat
de stack unattended draaien (kerneis).

```
Bezoeker ──HTTPS──► Cloudflare (DNS + WAF + Tunnel edge)
                          │  (cloudflared tunnel, geen open poorten)
                          ▼
                 ┌─────────────────────────────┐
                 │  Mac mini M4 (server-mini)   │
                 │  Docker Compose netwerk      │
                 │  ┌────────┐   ┌────────────┐ │
                 │  │ web    │──►│ postgres   │ │
                 │  │FastAPI │   │ (volume)   │ │
                 │  └───┬────┘   └────────────┘ │
                 │      │  cloudflared (sidecar) │
                 └──────┼──────────────────────┘
                        ▼
                 Transactionele e-mail (magic-link + admin-notificaties)
```

## Componenten
| Component | Doel | Locatie |
|-----------|------|---------|
| `web` | FastAPI app: routes, Jinja2-templates, htmx-partials, auth, admin | `app/` |
| `postgres` | Profielen, leden, tags, offerings/needs, posts | Docker service + volume |
| `cloudflared` | Cloudflare Tunnel — exposeert `web` zonder poortforwarding | Docker service |
| e-mail | Verzendt magic-links en goedkeurings-notificaties | externe provider (OPEN) |

## Data Flow — toegang & profiel (Fase 1)
1. Bezoeker vult open registratieformulier in (naam, e-mail) → status `pending`.
2. Admin (Richard) krijgt notificatie; keurt goed in admin-queue (één klik) → status `approved`.
3. Lid vraagt magic-link aan → ontvangt e-mail → klikt → server-side sessie.
4. Lid bewerkt profiel: over jezelf, wat je maakt (offerings), waar je naar zoekt (needs),
   tags/skills, en **zichtbaarheid per profiel** (default: alleen-leden).
5. Directory toont profielen volgens zichtbaarheid; publieke profielen krijgen een
   openbare URL + zijn indexeerbaar, besloten profielen `noindex` + alleen voor ingelogde leden.

## Datamodel (holistisch ontworpen, gefaseerd gevuld)
Ontworpen om alle vier visie-richtingen te dragen zonder herbouw:
- `member` (account: e-mail, status pending/approved/suspended, rol, magic-link tokens, sessies)
- `profile` (1:1 member: bio, "wat ik maak", visibility public/members, slug, completeness)
- `tag` + `profile_tag` (skills/interesses, voedt directory-filter én matchmaking)
- `offering` (wat een lid maakt/aanbiedt) en `need` (waar een lid naar zoekt) → matchmaking-basis
- `match` (suggestie offering↔need, Fase 3)
- `post` + `comment` (community, Fase 4)
- `audit_log` (goedkeuringen, zichtbaarheidswijzigingen — AVG-traceerbaarheid)

## Fasering
- **Fase 0** — Fundering: Docker Compose, Alembic, base-layout, Cloudflare Tunnel, healthcheck.
- **Fase 1 (MVP)** — Registratie → goedkeuring → magic-link → profiel bewerken → zichtbaarheid.
- **Fase 2** — Directory: doorzoekbaar/filterbaar, publieke profielpagina's, AVG-export/-delete.
- **Fase 3** — Matchmaking: offering↔need-koppeling + tag-suggesties.
- **Fase 4** — Community: posts/reacties + moderatie.
- **Fase 5** — Publieke showcase: etalage naar buiten, SEO, OG-tags.

## Operationele eisen (unattended)
- Nightly Postgres-backup (sluit aan op bestaande M1-backupserver-routine).
- Healthcheck-endpoint + container `restart: unless-stopped`.
- Geen handmatige stappen in normale werking behalve de goedkeurings-queue (lichtgewicht).
