#!/usr/bin/env bash
# Nachtelijke unattended jobs voor dewereldvan.ai — gegated op AI_ENRICH_ENABLED,
# idempotent, lage op-last. Aangeroepen door de LaunchAgent
# com.theuws.dewereldvan.nightly-jobs op de M4 (server-mini).
#
#   1. refresh_matches   — herrekent de vraag↔aanbod-matchsuggesties (Tier 1).
#   2. distill_memories  — werkt het sessie-overstijgend concierge-geheugen bij (F2).
#
# Bewust GEEN `set -e`: faalt job 1, dan moet job 2 alsnog draaien. Elke job is
# zelf best-effort (een fout in de AI-laag mag niets breken).
set -uo pipefail

APP_DIR="${DWV_APP_DIR:-$HOME/dewereldvan-app}"
DOCKER="${DOCKER_BIN:-/usr/local/bin/docker}"

cd "$APP_DIR" || { echo "FOUT: $APP_DIR niet gevonden"; exit 1; }

ts() { date '+%Y-%m-%d %H:%M:%S'; }
echo "=== $(ts) nightly-jobs start ==="

echo "--- $(ts) refresh_matches ---"
"$DOCKER" compose exec -T web python -m app.jobs.refresh_matches || \
  echo "WAARSCHUWING: refresh_matches eindigde met een fout"

echo "--- $(ts) distill_memories ---"
"$DOCKER" compose exec -T web python -m app.jobs.distill_memories || \
  echo "WAARSCHUWING: distill_memories eindigde met een fout"

echo "=== $(ts) nightly-jobs done ==="
