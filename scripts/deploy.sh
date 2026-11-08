#!/usr/bin/env bash
# deploy.sh — zet de gepushte main van dewereldvan.ai live op Hetzner (theuws-prod).
#
#   scripts/deploy.sh
#
# Wat het doet: controleert dat HEAD gelijk is aan origin/main, maakt een tar-backup van de app-map en een
# pg_dump van de live database, exporteert de commit (git archive, geen werkmap) en rsynct die naar
# /srv/apps/dewereldvan-app (.env blijft op de server staan), bouwt met docker compose op de server (amd64) en
# meldt pas "live" als /healthz de nieuwe VERSION teruggeeft. Migraties draaien bij de start (Dockerfile-CMD).
#
# Achtergrond: ~/Documents/server-mini-development/docs/HOSTING_HETZNER.md
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT"

HZ_HOST=theuws-prod
HZ_DIR=/srv/apps/dewereldvan-app
HZ_SRC_DIR="$PROJECT"
# shellcheck source=deploy-hetzner-lib.sh
source "$PROJECT/scripts/deploy-hetzner-lib.sh"

BACKUP_DIR=/srv/deploy-backups/hz/dewereldvan-app
KEEP_DUMPS=10

hz_check
hz_require_pushed_main
hz_backup

# Pre-deploy databasedump: de start draait `alembic upgrade head`, dus vóór een migratie altijd een terugweg.
# pipefail: een mislukte pg_dump mag niet als geldige (lege) gzip doorgaan.
dump="$BACKUP_DIR/db-$(date +%Y%m%d-%H%M%S).sql.gz"
ssh -o ConnectTimeout=10 "$HZ_HOST" \
    "set -o pipefail; cd $HZ_DIR && sudo -u deploy docker compose exec -T postgres pg_dump -U app dewereldvan | gzip | sudo tee $dump >/dev/null && sudo gunzip -c $dump | grep -q 'PostgreSQL database dump complete'" \
    || { ssh -n "$HZ_HOST" "sudo rm -f $dump"; hz_die "pg_dump vóór de deploy faalde"; }
hz_log "database-dump $dump"
ssh -n -o ConnectTimeout=10 "$HZ_HOST" \
    "cd $BACKUP_DIR && ls -1t -- db-*.sql.gz | tail -n +$((KEEP_DUMPS + 1)) | sudo xargs -r rm -f --" \
    || hz_log "let op: oude dumps opruimen in $BACKUP_DIR faalde"

src=$(hz_export_head)
# De versie en revisie komen uit de export, niet uit de werkmap: dat is wat er live gaat.
VERSION="$(tr -d '[:space:]' < "$src/VERSION")"
REVISION="$(tr -d '[:space:]' < "$src/REVISION")"
# /data/ en /teaser/ horen niet in de app-map op de server (data = named volume, teaser = buiten dienst).
hz_sync "$src" --exclude=/data/ --exclude=/teaser/
rm -rf "$src"

# Gaat het na dit punt mis, dan staat de terugweg op het scherm.
trap 'printf "\n[hz] Deploy niet bevestigd. Terugweg: backup %s/<laatste>.tar.gz en dump %s\n" "$BACKUP_DIR" "$dump" >&2' EXIT
hz_compose up -d --build
hz_wait_http "https://dewereldvan.ai/healthz" "\"revision\":\"$REVISION\""
trap - EXIT
hz_log "dewereldvan.ai $VERSION ($REVISION) staat live"
