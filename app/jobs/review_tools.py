"""Tools reviewen (AI-dossier per gebruikte tool) — periodiek, unattended.

Draai handmatig of via cron op de M4:

    docker compose exec -T web python -m app.jobs.review_tools

Reviewt elke tool die de drempel haalt (≥1 lid gebruikt 'm, valide url) maar geen
verse review heeft (nooit gereviewd óf > 90 dagen oud). Idempotent (al-verse
reviews worden overgeslagen); bewust periodiek i.p.v. synchroon (een markdown-fetch
+ LLM-call zou de bewerk-UX vertragen — de warme trigger doet de directe). Best-
effort: een fout per tool breekt de batch niet, een refusal/parse-fail laat de
oude review staan. Gegated op ``settings.ai_enrich_enabled``.
"""

from __future__ import annotations

import logging

from app.db import SessionLocal
from app.services import tool_review_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("review_tools")


def main() -> int:
    with SessionLocal() as db:
        reviewed = tool_review_service.refresh_all(db)
        db.commit()
    logger.info("Tools gereviewd: %s.", reviewed)
    return reviewed


if __name__ == "__main__":  # pragma: no cover
    main()
