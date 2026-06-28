#!/bin/bash
# Nightly pg_dump van de live dewereldvan Postgres → /Users/Shared/srv/backups
# (de map die de M1 nachtelijk ophaalt). Gepland via launchd
# (com.theuws.dewereldvan.backup, 03:00 — vóór de nightly-jobs van 03:30).
# 30-dagen-rotatie, gzip (de M4-schijf is krap). Volgt de server-mini-conventie:
# <project>-db-<stamp>.sql.gz naast de andere project-dumps.
#
# Credentials worden RUNTIME uit de draaiende container-env gelezen
# (POSTGRES_USER/_DB/_PASSWORD) — geen secret in de repo.
set -euo pipefail

# launchd draait met een minimale PATH; docker leeft in /usr/local/bin op server-mini.
export PATH="/usr/local/bin:$PATH"
export DOCKER_HOST=unix:///Users/server/.docker/run/docker.sock

CONTAINER=dewereldvan-app-postgres-1
OUT=/Users/Shared/srv/backups
STAMP=$(date +%Y%m%d-%H%M%S)
FILE="$OUT/dewereldvan-db-$STAMP.sql.gz"

# Dump naar een temp-bestand en promoveer alleen bij succes, zodat een mislukte run
# nooit een misleidend leeg/partieel bestand achterlaat.
trap 'rm -f "$FILE.tmp"' EXIT
docker exec "$CONTAINER" sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists' \
  | gzip > "$FILE.tmp"

# Sanity: een echte dump gzipt tot ruim boven 1 KB; vang een lege/partiële dump af.
if [ "$(gzip -dc "$FILE.tmp" | wc -c)" -lt 1000 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup FAILED: dump te klein (<1KB)" >&2
  exit 1
fi
mv "$FILE.tmp" "$FILE"

# Roteer: bewaar 30 dagen dumps.
find "$OUT" -name 'dewereldvan-db-*.sql.gz' -type f -mtime +30 -delete 2>/dev/null || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup ok: $(basename "$FILE") ($(wc -c < "$FILE") bytes)"
