"""Matchmaking herrekenen (Tier 1) — periodiek, unattended.

Draai handmatig of via cron op de M4:

    docker compose exec -T web python -m app.jobs.refresh_matches

Of nachtelijk via een cron/LaunchAgent (lage op-last; één Claude-call per need,
gegated op AI_ENRICH_ENABLED). De engine is idempotent — ``dismissed``/``acted``
blijven gerespecteerd.

NB (Fase 1): herrekenen gebeurt via deze periodieke run, NIET synchroon bij een
profiel-edit (een LLM-call per save zou de bewerk-UX vertragen). Een edit-trigger
(``match_service.refresh_for_member`` na een need/offering-wijziging, evt. async)
is een Fase-2-verfijning.
"""

from __future__ import annotations

import logging

from app.db import SessionLocal
from app.services import match_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("refresh_matches")


def main() -> int:
    with SessionLocal() as db:
        total = match_service.refresh_all(db)
        db.commit()
    logger.info("Matchmaking herrekend: %s verse suggesties geschreven.", total)
    return total


if __name__ == "__main__":  # pragma: no cover
    main()
