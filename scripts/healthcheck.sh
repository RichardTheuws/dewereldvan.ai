#!/bin/bash
# Externe uptime-check voor dewereldvan.ai — pingt /healthz DOOR de tunnel (dus
# tunnel + web + DB in één keer) en stuurt een Telegram-alert bij een toestands-
# WISSELING (down → ping, en weer up → herstel-ping). Bewust out-of-band: leest de
# bot-token uit ~/dewereldvan-app/.env en praat rechtstreeks met de Telegram-API,
# zodat de alert óók werkt als álle containers plat liggen (in tegenstelling tot
# notify_ops, dat de web-container nodig heeft).
#
# Gepland via launchd (com.theuws.dewereldvan.healthcheck, elke 5 min). De
# debounce (state-file) voorkomt dat een outage elke run opnieuw pingt.
set -uo pipefail

ENV_FILE="${DWV_ENV_FILE:-$HOME/dewereldvan-app/.env}"
URL="${DWV_HEALTH_URL:-https://dewereldvan.ai/healthz}"
STATE="${DWV_HEALTH_STATE:-/tmp/dewereldvan-health.state}"

env_val() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-; }

send() {  # $1 = bericht — best-effort, mag nooit hard falen
  local tok cid
  tok=$(env_val TELEGRAM_BOT_TOKEN)
  cid=$(env_val TELEGRAM_ADMIN_CHAT_ID)
  [ -n "$tok" ] && [ -n "$cid" ] || return 0
  curl -s --max-time 15 "https://api.telegram.org/bot${tok}/sendMessage" \
    --data-urlencode "chat_id=${cid}" \
    --data-urlencode "text=$1" >/dev/null 2>&1 || true
}

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$URL" 2>/dev/null || echo "000")
prev=$(cat "$STATE" 2>/dev/null || echo "up")
now=$(date '+%Y-%m-%d %H:%M:%S')

if [ "$code" = "200" ]; then
  if [ "$prev" != "up" ]; then
    send "✅ dewereldvan.ai is weer bereikbaar (/healthz 200) — $now"
  fi
  echo "up" > "$STATE"
else
  if [ "$prev" != "down" ]; then
    send "🔴 dewereldvan.ai ONBEREIKBAAR — /healthz gaf ${code} op ${now}. Check de M4 (containers/tunnel/DB)."
  fi
  echo "down" > "$STATE"
fi
echo "[$now] healthcheck: code=$code prev=$prev"
