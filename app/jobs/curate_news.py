"""Nieuws cureren ("De Briefing", doc 02) — wekelijks, unattended, mens-in-de-lus.

Draai handmatig of via cron op de M4 (wekelijks gegate in ``nightly-jobs.sh``):

    docker compose exec -T web python -m app.jobs.curate_news

Roept de ``news_curation_service`` aan (web_search/web_fetch op Opus 4.8) en
persisteert elk voorstel als ``Post`` met **``review_state=pending_review``** —
NOOIT live. Een admin keurt de shortlist daarna met één klik goed; pas dan wordt
een item publiek. Idempotent (dedup op URL via ``create_curated_news`` → een
dubbele run maakt geen dubbele items). Best-effort: een fout in de AI-laag breekt
niets (de service vangt 'm af en levert een lege lijst). Gegated op
``settings.ai_enrich_enabled``.

Optioneel: bij nieuwe kandidaten een in-app "klaar"-chip (state-derived) +
een best-effort Telegram-push naar de admins ("N nieuws-kandidaten klaar").
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Post, PostKind
from app.security import naive_utc, utcnow
from app.services import news_curation_service, notification_service, post_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("curate_news")


def _existing_news_id(db, url: str) -> int | None:
    """De id van een al bestaand nieuws-item op deze URL (voor dedup-telling), of
    None. Spiegelt de idempotentie-poort in ``create_curated_news``."""
    clean = (url or "").strip()[:500]
    if not clean:
        return None
    return db.scalar(
        select(Post.id).where(Post.kind == PostKind.nieuws, Post.url == clean)
    )


def _notify_admins(db, count: int) -> None:
    """Best-effort push naar de admins dat er een shortlist klaarstaat — via
    **Telegram** (admin-communicatie loopt niet via e-mail). De in-app pull-chip
    dekt de admin-pagina sowieso; deze push raakt admins met een gekoppelde
    Telegram. Faalt nooit hard."""
    if count <= 0:
        return
    meervoud = count != 1
    body = (
        f"{count} gecureerde {'items' if meervoud else 'item'} "
        f"wacht{'en' if meervoud else ''} op je goedkeuring."
    )
    notification_service.notify_admins(
        db,
        notification_service.Notification(
            kind="news_shortlist",
            title="Nieuws-kandidaten klaar",
            body=body,
            url="/admin/nieuws",
            action_label="Beoordeel",
        ),
    )


def main() -> int:
    """Cureer + persisteer de kandidaten als ``pending_review``. Returnt het aantal
    nieuw aangemaakte voorstellen (dedup-hits tellen niet mee)."""
    if not settings.ai_enrich_enabled:
        logger.info("curate_news: AI-curatie staat uit; niets te doen.")
        return 0

    created = 0
    with SessionLocal() as db:
        candidates = news_curation_service.curate(db)
        week = post_service.iso_week_anchor(naive_utc(utcnow()))
        for c in candidates:
            pre_id = _existing_news_id(db, c.url)
            post = post_service.create_curated_news(
                db,
                title=c.title,
                url=c.url,
                ai_take=c.ai_take,
                ai_relevance=c.ai_relevance,
                source=c.source,
                briefing_week=week,
            )
            # Nieuw ⟺ er bestond nog geen item op deze URL (dedup-hit telt niet mee).
            if pre_id is None and post.id is not None:
                created += 1
        db.commit()
        # Notificeer pas ná commit (de chip is state-derived; de push best-effort).
        try:
            _notify_admins(db, created)
        except Exception:  # noqa: BLE001 — een seintje mag de job nooit breken
            logger.warning("curate_news: admin-notificatie overgeslagen.", exc_info=True)

    logger.info("Nieuws-kandidaten voorgesteld (pending_review): %s.", created)
    return created


if __name__ == "__main__":  # pragma: no cover
    main()
