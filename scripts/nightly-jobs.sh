#!/usr/bin/env bash
# Nachtelijke unattended jobs voor dewereldvan.ai — gegated op AI_ENRICH_ENABLED,
# idempotent, lage op-last. Aangeroepen door de LaunchAgent
# com.theuws.dewereldvan.nightly-jobs op de M4 (server-mini).
#
#   1. refresh_matches   — herrekent de vraag↔aanbod-matchsuggesties (Tier 1).
#   2. distill_memories  — werkt het sessie-overstijgend concierge-geheugen bij (F2).
#   3. enrich_projects   — screenshot-hero + AI-samenvatting op de projectpagina's.
#   4. enrich_tool_logos — best-effort favicon/og:image-logo per tool-URL.
#   5. curate_news       — WEKELIJKS (zondag): stelt de nieuws-briefing voor als
#                          pending_review (mens-in-de-lus; nooit silent-publish).
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

echo "--- $(ts) enrich_projects ---"
"$DOCKER" compose exec -T web python -m app.jobs.enrich_projects || \
  echo "WAARSCHUWING: enrich_projects eindigde met een fout"

echo "--- $(ts) enrich_tool_logos ---"
"$DOCKER" compose exec -T web python -m app.jobs.enrich_tool_logos || \
  echo "WAARSCHUWING: enrich_tool_logos eindigde met een fout"

# Wekelijkse gate: nieuws-curatie draait ALLEEN op zondag (date +%u == 7).
# "Schaarste = signaal" — dagelijks zou te veel admin-poort-werk en lauwe items
# geven. Best-effort (geen `set -e`-breuk); de job is zelf idempotent + faal-veilig.
if [ "$(date +%u)" = "7" ]; then
  echo "--- $(ts) curate_news (wekelijks, zondag) ---"
  "$DOCKER" compose exec -T web python -m app.jobs.curate_news || \
    echo "WAARSCHUWING: curate_news eindigde met een fout"
else
  echo "--- $(ts) curate_news overgeslagen (alleen zondag) ---"
fi

echo "=== $(ts) nightly-jobs done ==="
