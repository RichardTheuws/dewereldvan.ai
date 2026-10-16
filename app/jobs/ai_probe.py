"""Maandelijkse AI-steekproef (PRD hub §4.4) — unattended.

    docker compose exec -T web python -m app.jobs.ai_probe

Draait via nightly-jobs.sh alleen op de 1e van de maand; idempotent per maand
(al-gemeten vragen worden overgeslagen, dus een herhaalde run kost niets extra).
Gegated op AI_ENRICH_ENABLED.
"""

from __future__ import annotations

import logging

from app.db import SessionLocal
from app.services import ai_probe_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_probe")


def main() -> int:
    with SessionLocal() as db:
        made = ai_probe_service.run_month(db)
    logger.info("AI-steekproef: %s nieuwe metingen.", made)
    return made


if __name__ == "__main__":  # pragma: no cover
    main()
