#!/usr/bin/env bash
# Nachtelijke unattended jobs voor dewereldvan.ai — gegated op AI_ENRICH_ENABLED,
# idempotent, lage op-last. Aangeroepen door de LaunchAgent
# com.theuws.dewereldvan.nightly-jobs op de M4 (server-mini).
#
#   1. refresh_matches   — herrekent de vraag↔aanbod-matchsuggesties (Tier 1).
#   2. distill_memories  — werkt het sessie-overstijgend concierge-geheugen bij (F2).
#   3. enrich_projects   — screenshot-hero + AI-samenvatting op de projectpagina's.
#   4. enrich_tool_logos — best-effort favicon/og:image-logo per tool-URL.
#   5. review_tools      — AI-dossier per ≥1-gebruiker-tool (re-review na 90 dagen).
#   6. curate_news       — WEKELIJKS (zondag): stelt de nieuws-briefing voor als
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

# Verzamel gefaalde jobs zodat we aan het eind ÉÉN Telegram-ping sturen i.p.v.
# een storing stil in een logfile te laten verdwijnen (unattended-operator).
FAILED=()
run_job() {  # run_job <naam> <module>
  echo "--- $(ts) $1 ---"
  if ! "$DOCKER" compose exec -T web python -m "$2"; then
    echo "WAARSCHUWING: $1 eindigde met een fout"
    FAILED+=("$1")
  fi
}

run_job refresh_matches    app.jobs.refresh_matches
run_job distill_memories   app.jobs.distill_memories
run_job enrich_projects    app.jobs.enrich_projects
run_job enrich_tool_logos  app.jobs.enrich_tool_logos
run_job review_tools       app.jobs.review_tools

# Wekelijkse gate: nieuws-curatie draait ALLEEN op zondag (date +%u == 7).
# "Schaarste = signaal" — dagelijks zou te veel admin-poort-werk en lauwe items
# geven. Best-effort (geen `set -e`-breuk); de job is zelf idempotent + faal-veilig.
if [ "$(date +%u)" = "7" ]; then
  run_job curate_news app.jobs.curate_news
else
  echo "--- $(ts) curate_news overgeslagen (alleen zondag) ---"
fi

# Wekelijkse gate: agenda-curatie draait ALLEEN op maandag (date +%u == 1), los
# van de nieuws-curatie (zondag) zodat de twee AI-tool-loops elkaar niet kruisen.
# AI keurt het zekere automatisch goed (live); twijfel → /admin/agenda. Best-effort.
if [ "$(date +%u)" = "1" ]; then
  run_job curate_events app.jobs.curate_events
else
  echo "--- $(ts) curate_events overgeslagen (alleen maandag) ---"
fi

# Eén consolidated seintje bij ≥1 gefaalde job (best-effort; mag de run niet breken).
if [ "${#FAILED[@]}" -gt 0 ]; then
  MSG="Nightly-jobs: $(IFS=', '; echo "${FAILED[*]}") faalde(n) op $(ts)."
  echo "$MSG"
  "$DOCKER" compose exec -T web python -m app.jobs.notify_ops "$MSG" \
    || echo "WAARSCHUWING: kon ops-melding niet versturen"
fi

echo "=== $(ts) nightly-jobs done ==="
