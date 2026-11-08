# Backup & Restore — dewereldvan.ai

De volledige platform-staat zit in één Postgres-database (`dewereldvan`, container
`dewereldvan-app-postgres-1` op Hetzner `theuws-prod`, sinds 2026-11-04). Profielen, leden, projecten, agenda,
nieuws, ideeën — alles. Eén kapot volume zonder backup = alles weg. Daarom:

## Hoe het nu beschermd is

- **Nachtelijke dump** door de host (systemd-timer `db-dump`, 03:30, infra-repo):
  `/srv/infra/dumps/dewereldvan-app-postgres-1.sql.gz` op `theuws-prod` (alleen root leesbaar).
- **Off-site**: `restic-backup` (04:00) naar de eigen Storage Box en R2-EU, plus Hetzner-snapshots.
- **Bij elke deploy**: `scripts/deploy.sh` maakt vooraf een `pg_dump` in
  `/srv/deploy-backups/hz/dewereldvan-app/db-<timestamp>.sql.gz`.

Het M1-systeem (`m4-backup.sh`) en `scripts/backup-db.sh` (LaunchAgent op de M4) horen bij de oude M4-opzet en
dekken de Hetzner-database niet.

## Een verse dump nu maken (handmatig, buiten het schema om)

```bash
ssh theuws-prod "cd /srv/apps/dewereldvan-app && sudo -u deploy docker compose exec -T postgres \
  pg_dump -U app dewereldvan" | gzip > dewereldvan-$(date +%F).sql.gz
```

## Restore

> Een restore is **destructief** voor de doel-DB. Doe 'm altijd eerst tegen een
> wegwerp-DB (dry-run) en vergelijk rij-aantallen vóór je productie aanraakt.

### 1. Dry-run (bewijs dat de dump goed is) — tegen een wegwerp-Postgres

```bash
docker run -d --name dwv-restore-test \
  -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app -e POSTGRES_DB=dewereldvan \
  postgres:16
# wacht tot healthy: docker exec dwv-restore-test pg_isready -U app -d dewereldvan
gunzip -c dewereldvan-YYYY-MM-DD.sql.gz | docker exec -i dwv-restore-test \
  psql -U app -d dewereldvan -q
docker exec dwv-restore-test psql -U app -d dewereldvan -tA \
  -c "select 'member='||count(*) from member union all select 'post='||count(*) from post;"
docker rm -f dwv-restore-test
```

Vergelijk de aantallen met de live DB; gelijk = de dump is goed.

### 2. Productie-restore (alleen bij echt verlies)

```bash
# kies de dump: de nachtelijke (/srv/infra/dumps/...) of een pre-deploy-dump (/srv/deploy-backups/hz/dewereldvan-app/)
# herstel in de draaiende DB (na een DROP/CREATE van het schema indien nodig)
ssh theuws-prod "cd /srv/apps/dewereldvan-app && sudo gunzip -c <dump>.sql.gz | \
  sudo -u deploy docker compose exec -T postgres psql -U app -d dewereldvan -q"
```

## Geverifieerd

- 2026-06-19: dump-keten end-to-end bewezen — `pg_dump` → gzip → restore in wegwerp-Postgres,
  rij-aantallen identiek aan live (member/profile/post/offering). Nachtelijke M1-job draait de
  dewereldvan-dump (geverifieerd: bestand landt, valide gzip, log "OK").

## Testketen-pariteit (gerelateerd)

De snelle test-suite draait op SQLite en mist dialect-bugs. `tests/test_postgres_parity.py`
+ `scripts/test-postgres.sh` + de CI-workflow draaien `alembic upgrade head` + smoke-CRUD tegen
een **echte Postgres** zodat migratie-bugs (varchar-lengte, boolean-default, type-mismatch) vóór
deploy rood worden i.p.v. in productie. Zie `scripts/test-postgres.sh`.
