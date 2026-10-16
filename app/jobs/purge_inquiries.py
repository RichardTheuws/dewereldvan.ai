"""Aanvragen ouder dan 180 dagen wissen (PRD hub §4.1) — nachtelijk, unattended.

    docker compose exec -T web python -m app.jobs.purge_inquiries

Nul AI, dus niet gegated op AI_ENRICH_ENABLED. Houdt de belofte uit het
toestemmingsvinkje ("we bewaren ze 180 dagen").
"""

from __future__ import annotations

import logging

from app.db import SessionLocal
from app.services import inquiry_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("purge_inquiries")


def main() -> int:
    with SessionLocal() as db:
        removed = inquiry_service.purge_expired(db)
        db.commit()
    logger.info(
        "Aanvragen gewist (ouder dan %s dagen): %s", inquiry_service.RETENTION_DAYS, removed
    )
    return removed


if __name__ == "__main__":  # pragma: no cover
    main()
