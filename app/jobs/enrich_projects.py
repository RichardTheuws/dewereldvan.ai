"""Projecten verrijken (screenshot-hero + AI-samenvatting) — periodiek, unattended.

Draai handmatig of via cron op de M4:

    docker compose exec -T web python -m app.jobs.enrich_projects

Vult voor elke offering met een URL maar zonder verrijking een screenshot
(Cloudflare Browser Rendering) + een gegronde samenvatting (uit de pagina-
markdown). Idempotent (al-verrijkte projecten worden overgeslagen); bewust
periodiek i.p.v. synchroon bij opslaan (een screenshot + LLM-call zou de
bewerk-UX vertragen). Best-effort: een fout per project breekt de batch niet.
"""

from __future__ import annotations

import logging

from app.db import SessionLocal
from app.services import project_enrich_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enrich_projects")


def main() -> int:
    with SessionLocal() as db:
        enriched = project_enrich_service.refresh_all(db)
        db.commit()
    logger.info("Projecten verrijkt: %s.", enriched)
    return enriched


if __name__ == "__main__":  # pragma: no cover
    main()
