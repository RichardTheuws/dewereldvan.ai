# Backup & Restore — dewereldvan.ai

De volledige platform-staat zit in één Postgres-database (`dewereldvan`, container
`dewereldvan-app-postgres-1` op de M4). Profielen, leden, projecten, agenda, nieuws,
ideeën — alles. Eén kapot volume zonder backup = alles weg. Daarom:

## Hoe het nu beschermd is

dewereldvan is geregistreerd in het **bestaande nachtelijke M1-backupsysteem**
(`/Users/Shared/srv/monitoring/m4-backup.sh`, LaunchAgent `com.server-mini.m4-backup`,
elke dag 02:00). Dat systeem doet al maanden de andere stacks (boekhoudr, n8n, …) en
levert gratis: **logische `pg_dump`, gzip, size-validatie, daily/weekly-retentie
(7 dagen / 4 weken), ntfy-alerting bij falen, en een freshness-heartbeat naar de M4.**

dewereldvan staat in de `PG_DATABASES`-array van dat script:

```
"dewereldvan-app-postgres-1:app:dewereldvan"
```

De dump landt nachtelijks op de M1 in:

```
/Users/Shared/srv/backups/m4/daily/<YYYY-MM-DD>/postgres/dewereldvan.sql.gz
/Users/Shared/srv/backups/m4/weekly/<YYYY-MM-DD>/postgres/dewereldvan.sql.gz   # zondags
```

> **Niet** een aparte cron op de M4 — bewust geaugmenteerd op het beproefde M1-systeem
> i.p.v. een tweede, ongeteste backup-stack ernaast.

## Een verse dump nu maken (handmatig, buiten het schema om)

```bash
ssh server-mini "cd ~/dewereldvan-app && docker compose exec -T postgres \
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
# haal de dump van de M1 (de M4 kent de M1-hostname niet; doe dit vanaf je laptop)
scp server-mini-m1:/Users/Shared/srv/backups/m4/daily/<DATUM>/postgres/dewereldvan.sql.gz .
# zet 'm op de M4
scp dewereldvan.sql.gz server-mini:~/
# herstel in de draaiende DB (na een DROP/CREATE van het schema indien nodig)
ssh server-mini "cd ~/dewereldvan-app && gunzip -c ~/dewereldvan.sql.gz | \
  docker compose exec -T postgres psql -U app -d dewereldvan -q"
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
