"""Agenda cureren (plan Increment 3) — wekelijks, unattended, AI keurt het zekere.

Draai handmatig of via cron op de M4 (wekelijks gegate in ``nightly-jobs.sh``):

    docker compose exec -T web python -m app.jobs.curate_events

Roept de ``event_curation_service`` aan (web_search/web_fetch op Opus 4.8 — vindt
ECHTE NL/BE AI-events, nooit verzonnen) en persisteert elke kandidaat als ``Post``:

- **zeker** (``auto_approvable``: hoge confidence + geldige datum + locatie) →
  direct ``live`` op de agenda;
- **twijfel** → ``pending_review`` in de admin-queue (``/admin/agenda``).

Idempotent (dedup op URL via ``create_curated_event`` → een dubbele run maakt geen
dubbele events). Best-effort: een fout in de AI-laag breekt niets (de service vangt
'm af, levert een lege lijst → niets gepubliceerd). Gegated op ``ai_enrich_enabled``.

Na afloop: een best-effort Telegram-push naar de admins met hoeveel events live
gingen en hoeveel op goedkeuring wachten.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Post, PostKind
from app.services import event_curation_service, notification_service, post_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("curate_events")


def _existing_event_id(db, url: str) -> int | None:
    """De id van een al bestaand event op deze URL (voor dedup-telling), of None."""
    clean = (url or "").strip()[:500]
    if not clean:
        return None
    return db.scalar(
        select(Post.id).where(Post.kind == PostKind.event, Post.url == clean)
    )


def _notify_admins(db, *, live: int, pending: int) -> None:
    """Best-effort Telegram-push: hoeveel events live gingen + hoeveel wachten op
    goedkeuring. Faalt nooit hard. Niets nieuws → geen seintje."""
    if live <= 0 and pending <= 0:
        return
    parts = []
    if live:
        parts.append(f"{live} event{'s' if live != 1 else ''} automatisch op de agenda")
    if pending:
        parts.append(
            f"{pending} event{'s' if pending != 1 else ''} wacht"
            f"{'en' if pending != 1 else ''} op je goedkeuring"
        )
    notification_service.notify_admins(
        db,
        notification_service.Notification(
            kind="event_curation",
            title="Agenda-curatie klaar",
            body=" · ".join(parts) + ".",
            url="/admin/agenda" if pending else "/agenda",
            action_label="Beoordeel" if pending else "Bekijk",
        ),
    )


def main() -> int:
    """Cureer + persisteer de events (zeker → live, twijfel → pending). Returnt het
    aantal nieuw aangemaakte events (dedup-hits tellen niet mee)."""
    if not settings.ai_enrich_enabled:
        logger.info("curate_events: AI-curatie staat uit; niets te doen.")
        return 0

    created = live_count = pending_count = 0
    with SessionLocal() as db:
        candidates = event_curation_service.curate(db)
        for c in candidates:
            pre_id = _existing_event_id(db, c.url)
            live = event_curation_service.auto_approvable(c)
            post = post_service.create_curated_event(
                db,
                title=c.title,
                url=c.url,
                category=c.category,
                frequency=c.frequency,
                confidence=c.confidence,
                live=live,
                next_at=c.next_at,
                location=c.location,
                cadence_note=c.cadence_note,
                description=c.description,
                source=c.source,
            )
            if pre_id is None and post.id is not None:
                created += 1
                if live:
                    live_count += 1
                else:
                    pending_count += 1
        db.commit()
        try:
            _notify_admins(db, live=live_count, pending=pending_count)
        except Exception:  # noqa: BLE001 — een seintje mag de job nooit breken
            logger.warning("curate_events: admin-notificatie overgeslagen.", exc_info=True)

    logger.info(
        "Agenda-curatie: %s nieuw (%s live, %s pending).",
        created,
        live_count,
        pending_count,
    )
    return created


if __name__ == "__main__":  # pragma: no cover
    main()
