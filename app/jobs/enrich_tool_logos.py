"""Tool-logo's verrijken — best-effort favicon/og:image per tool-URL, unattended.

Draai handmatig of via cron op de M4:

    docker compose exec -T web python -m app.jobs.enrich_tool_logos

Vult voor elke tool met een URL maar zonder ``logo_url`` een best-effort logo
(favicon/og:image → WEBP). Idempotent (al-verrijkte tools worden overgeslagen);
bewust periodiek i.p.v. synchroon bij opslaan (een logo-fetch zou de bewerk-UX
vertragen en gaf een pre-commit-race). Best-effort: een fout per tool breekt de
batch niet.
"""

from __future__ import annotations

import logging

from app.db import SessionLocal
from app.services import logo_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enrich_tool_logos")


def main() -> int:
    with SessionLocal() as db:
        enriched = logo_service.refresh_all(db)
        db.commit()
    logger.info("Tool-logo's verrijkt: %s.", enriched)
    return enriched


if __name__ == "__main__":  # pragma: no cover
    main()
