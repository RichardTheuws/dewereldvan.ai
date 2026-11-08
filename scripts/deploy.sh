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

VERSION="$(tr -d '[:space:]' < VERSION)"

hz_check
hz_require_pushed_main
hz_backup

# Pre-deploy databasedump: de start draait `alembic upgrade head`, dus vóór een migratie altijd een terugweg.
dump="/srv/deploy-backups/hz/dewereldvan-app/db-$(date +%Y%m%d-%H%M%S).sql.gz"
ssh -o ConnectTimeout=10 "$HZ_HOST" \
    "cd $HZ_DIR && sudo -u deploy docker compose exec -T postgres pg_dump -U app dewereldvan | gzip | sudo tee $dump >/dev/null && sudo test -s $dump" \
    || hz_die "pg_dump vóór de deploy faalde"
hz_log "database-dump $dump"

src=$(hz_export_head)
hz_sync "$src" --exclude=/teaser/
rm -rf "$src"

hz_compose up -d --build
hz_wait_http "https://dewereldvan.ai/healthz" "\"version\":\"$VERSION\""
hz_log "dewereldvan.ai $VERSION staat live"
