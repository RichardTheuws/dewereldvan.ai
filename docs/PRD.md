# PRD — dewereldvan.ai

**Versie**: 0.1.0
**Datum**: 2026-06-17
**Status**: 🟡 APPROVAL PENDING (Fase 0 start ná akkoord)

## 1. Doel
Een platform waar leden van een WhatsApp-groep een profiel aanmaken (wie ze zijn, wat ze
maken, waar ze naar op zoek zijn). Het MVP levert profielen + ledengids; het platform groeit
naar matchmaking, community en een publieke showcase — op één holistisch datamodel.

## 2. Doelgroep
Leden van een bestaande WhatsApp-groep. Toegang via open registratie met handmatige goedkeuring.

## 3. Scope per fase

### Fase 0 — Fundering
- Docker Compose: `web` (FastAPI) + `postgres` + `cloudflared`.
- Alembic, base-layout (Jinja2 + Tailwind + htmx), healthcheck, env-config.
- Cloudflare Tunnel koppelen aan `dewereldvan.ai`.
- **Succescriterium**: lege app live op `https://dewereldvan.ai` via Tunnel, healthcheck groen.

### Fase 1 — MVP: profielen
- Open registratie (naam, e-mail) → status `pending`.
- Admin-queue: goedkeuren/weigeren (één klik) + notificatie naar admin.
- Passwordless magic-link login (signed token, vervaltijd) + server-side sessie.
- Profiel bewerken: bio/over jezelf, "wat ik maak", "waar ik naar zoek", tags, zichtbaarheid.
- Zichtbaarheid per profiel (publiek / alleen-leden), default alleen-leden.
- **Succescriterium**: een goedgekeurd lid maakt en publiceert een profiel, kiest zichtbaarheid,
  en logt later opnieuw in via magic-link — zonder handmatige tussenkomst.

### Fase 2 — Directory
- Doorzoekbare/filterbare ledengids (op tag, "maakt", "zoekt").
- Publieke profielpagina's (respecteert zichtbaarheid; `noindex` voor besloten).
- AVG: data-export + verwijderrecht (self-service).

### Fase 3 — Matchmaking
- Koppeling offering ↔ need; tag-gebaseerde suggesties; "wie zoekt wat ik maak".

### Fase 4 — Community
- Posts/updates + reacties; lichte moderatie (admin verwijderen/verbergen).

### Fase 5 — Publieke showcase
- Etalage naar buiten: uitgelichte profielen/werk, SEO, OG-tags.

## 4. Edge cases & risico's (vooraf benoemd)
- **Dubbele registratie** (zelfde e-mail): idempotent — hervat bestaande flow, geen duplicaat.
- **Spam-registraties**: rate-limit + admin keurt; pending verloopt automatisch na X dagen.
- **E-mail-bezorging faalt**: magic-link/notificatie retry + zichtbare foutstatus; geen silent fail.
- **Magic-link**: eenmalig, korte TTL, gebonden aan e-mail; hergebruik/expired → nette her-aanvraag.
- **Zichtbaarheid publiek→besloten**: profiel direct delisten + `noindex`; eventueel cache-purge.
- **Lid verlaat WhatsApp-groep**: geen automatische koppeling; admin kan account `suspended` zetten.
- **AVG**: minimale data, expliciete instemming bij publiek zetten, export + delete (Fase 2).
- **Verlaten pending-accounts**: opschoning na vervaltermijn.
- **Onvolledige profielen**: completeness-indicator; besloten tot ingevuld.

## 5. Niet in scope (nu)
- Native mobiele app, betalingen, realtime chat (WhatsApp blijft het chatkanaal).

## 6. Open beslissing
- **Transactionele e-mailprovider** (Resend / Postmark / eigen SMTP) — beslissen vóór Fase 1.

## 7. Succes van het geheel
Leden onderhouden zelf hun profiel; Richard hoeft alleen nieuwe leden goed te keuren; het
platform draait unattended op de M4 achter Cloudflare Tunnel met nightly backups.
