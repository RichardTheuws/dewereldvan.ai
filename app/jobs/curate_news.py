"""Nieuws cureren ("De Briefing", doc 02) — wekelijks, unattended, mens-in-de-lus.

Draai handmatig of via cron op de M4 (wekelijks gegate in ``nightly-jobs.sh``):

    docker compose exec -T web python -m app.jobs.curate_news

Roept de ``news_curation_service`` aan (web_search/web_fetch op Opus 4.8) en
persisteert elk voorstel als ``Post``: **zeker** (``auto_approvable``:
relevantie ≥ ``AUTO_APPROVE_THRESHOLD``) → direct ``live``; **twijfel** →
``pending_review`` in ``/admin/nieuws`` (spiegelt de agenda-curatie, v0.116.0).
Idempotent (dedup op URL via ``create_curated_news`` → een dubbele run maakt
geen dubbele items). Best-effort: een fout in de AI-laag breekt niets (de
service vangt 'm af en levert een lege lijst). Gegated op
``settings.ai_enrich_enabled``.

Optioneel: bij nieuwe kandidaten een in-app "klaar"-chip (state-derived) +
een best-effort Telegram-push naar de admins ("N nieuws-kandidaten klaar").
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Post, PostKind, PostReviewState
from app.security import naive_utc, utcnow
from app.services import news_curation_service, notification_service, post_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("curate_news")


def _existing_news_id(db, url: str) -> int | None:
    """De id van een al bestaand nieuws-item op deze URL (voor dedup-telling), of
    None. Spiegelt de idempotentie-poort in ``create_curated_news`` — inclusief de
    URL-normalisatie, anders telt een dedup-hit onterecht als 'nieuw'."""
    clean = post_service._normalize_news_url(url)[:500]
    if not clean:
        return None
    return db.scalar(
        select(Post.id).where(Post.kind == PostKind.nieuws, Post.url == clean)
    )


def _notify_admins(db, count: int, live: int = 0) -> None:
    """Best-effort push naar de admins dat er een shortlist klaarstaat — via
    **Telegram** (admin-communicatie loopt niet via e-mail). De in-app pull-chip
    dekt de admin-pagina sowieso; deze push raakt admins met een gekoppelde
    Telegram. Faalt nooit hard."""
    if count <= 0 and live <= 0:
        return
    parts = []
    if live:
        parts.append(f"{live} {'items' if live != 1 else 'item'} automatisch in het nieuws")
    if count:
        parts.append(
            f"{count} gecureerde {'items' if count != 1 else 'item'} "
            f"wacht{'en' if count != 1 else ''} op je goedkeuring"
        )
    body = " · ".join(parts) + "."
    notification_service.notify_admins(
        db,
        notification_service.Notification(
            kind="news_shortlist",
            title="Nieuws-kandidaten klaar",
            body=body,
            url="/admin/nieuws" if count else "/nieuws",
            action_label="Beoordeel" if count else "Bekijk",
        ),
    )


def main() -> int:
    """Cureer + persisteer de kandidaten als ``pending_review``. Returnt het aantal
    nieuw aangemaakte voorstellen (dedup-hits tellen niet mee)."""
    if not settings.ai_enrich_enabled:
        logger.info("curate_news: AI-curatie staat uit; niets te doen.")
        return 0

    created = live_count = 0
    with SessionLocal() as db:
        candidates = news_curation_service.curate(db)
        # Retry-on-empty: het model haakt soms af met een lege lijst terwijl er wél
        # nieuws is (run-to-run-variantie). Op een web vol AI-nieuws is een lege
        # briefing vrijwel altijd een misser, geen deugd → één herkansing.
        if not candidates:
            logger.info("curate_news: lege eerste run — één herkansing.")
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
                live=news_curation_service.auto_approvable(c),
            )
            # Nieuw ⟺ er bestond nog geen item op deze URL (dedup-hit telt niet mee).
            if pre_id is None and post.id is not None:
                if post.review_state == PostReviewState.live:
                    live_count += 1
                else:
                    created += 1
        db.commit()
        # Notificeer pas ná commit (de chip is state-derived; de push best-effort).
        try:
            _notify_admins(db, created, live_count)
        except Exception:  # noqa: BLE001 — een seintje mag de job nooit breken
            logger.warning("curate_news: admin-notificatie overgeslagen.", exc_info=True)

    logger.info(
        "Nieuws: %s automatisch live, %s voorgesteld (pending_review).", live_count, created
    )
    return created + live_count


if __name__ == "__main__":  # pragma: no cover
    main()
