"""Concierge-geheugen distilleren (Fase 2) — periodiek, unattended.

Draai handmatig of via cron op de M4:

    docker compose exec -T web python -m app.jobs.distill_memories

Werkt het gedistilleerde ``member_memory`` bij voor elk lid met nieuwe
concierge-turns (idempotent via het hoogwatermerk; één goedkope Claude-call per
lid, gegated op AI_ENRICH_ENABLED). Bewust periodiek i.p.v. synchroon bij elk
antwoord: een LLM-call in de stream zou de UX vertragen en de EventSource sluit
op ``done``. Geheugen is voor latere sessies, dus minuten-latency is irrelevant.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.db import SessionLocal
from app.services import member_memory_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("distill_memories")


def main() -> int:
    if not settings.ai_enrich_enabled:
        logger.info("AI_ENRICH_ENABLED uit — geheugen-distill overgeslagen.")
        return 0
    with SessionLocal() as db:
        updated = member_memory_service.refresh_all(db)
        db.commit()
    logger.info("Concierge-geheugen bijgewerkt voor %s leden.", updated)
    return updated


if __name__ == "__main__":  # pragma: no cover
    main()
