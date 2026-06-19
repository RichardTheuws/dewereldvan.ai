"""Post-service — agenda-events + nieuws: plaatsen, weergeven, modereren.

Eén holistische entiteit (``Post``) met ``kind`` ∈ {event, nieuws}. Elk
goedgekeurd lid plaatst direct zichtbaar (geen wachtrij); een per-lid rate-limit
in een glijdend uur-venster dempt rommel (spiegelt ``idea_service``), admin kan
verbergen (``hidden``).

Sortering (de "verbazen"-ervaring):
- **events** — aankomend eerst (op ``next_at``), dan terugkerend-zonder-datum,
  dan verlopen achteraan. In Python gesorteerd zodat NULL/verleden netjes vallen.
- **nieuws** — nieuwste publicatie eerst (``published_at``, val terug op
  ``created_at``).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AuditAction,
    AuditLog,
    EventFrequency,
    Member,
    NewsRole,
    Post,
    PostKind,
)
from app.security import naive_utc, utcnow

__all__ = [
    "PostRateLimited",
    "check_post_rate_limit",
    "create_event",
    "create_news",
    "list_events",
    "list_news",
    "get_visible",
    "set_hidden",
    "relatieve_tijd",
    "nl_datum",
]

_DUTCH_MONTHS = [
    "", "jan", "feb", "mrt", "apr", "mei", "jun",
    "jul", "aug", "sep", "okt", "nov", "dec",
]


def relatieve_tijd(value: datetime | None, *, now: datetime | None = None) -> str:
    """Leesbare relatieve tijd t.o.v. nu: 'vandaag' / 'morgen' / 'over 3 dagen' /
    'volgende week' / een datum verderweg; verleden → 'geweest'. Jinja-filter."""
    if value is None:
        return ""
    now = naive_utc(now or utcnow())
    value_n = naive_utc(value)
    delta_days = (value_n.date() - now.date()).days
    if delta_days < 0:
        return "geweest"
    if delta_days == 0:
        return "vandaag"
    if delta_days == 1:
        return "morgen"
    if delta_days < 7:
        return f"over {delta_days} dagen"
    if delta_days < 14:
        return "volgende week"
    if delta_days < 31:
        weken = delta_days // 7
        return f"over {weken} weken"
    return nl_datum(value_n)


def nl_datum(value: datetime | None) -> str:
    """Absolute datum in Nederlands kort formaat ('12 jun 2026'). Jinja-filter."""
    if value is None:
        return ""
    return f"{value.day} {_DUTCH_MONTHS[value.month]} {value.year}"


class PostRateLimited(RuntimeError):
    """Het lid overschreed de plaats-rate-limit binnen het uur-venster."""


# --------------------------------------------------------------------------- #
# Rate-limit (per lid, glijdend uur-venster — over events + nieuws samen)     #
# --------------------------------------------------------------------------- #


def _recent_post_count(db: Session, member_id: int, now: datetime) -> int:
    window_start = naive_utc(now) - timedelta(hours=1)
    return (
        db.scalar(
            select(func.count())
            .select_from(Post)
            .where(
                Post.added_by_id == member_id,
                Post.created_at >= window_start,
            )
        )
        or 0
    )


def check_post_rate_limit(
    db: Session,
    member: Member,
    *,
    now: datetime | None = None,
) -> None:
    """Raise ``PostRateLimited`` als het lid het uur-budget overschreed."""
    now = now or utcnow()
    if _recent_post_count(db, member.id, now) >= settings.rate_limit_post_per_hour:
        raise PostRateLimited()


# --------------------------------------------------------------------------- #
# Plaatsen                                                                     #
# --------------------------------------------------------------------------- #


def create_event(
    db: Session,
    *,
    member: Member,
    title: str,
    frequency: EventFrequency,
    description: str | None = None,
    url: str | None = None,
    location: str | None = None,
    cadence_note: str | None = None,
    next_at: datetime | None = None,
) -> Post:
    """Plaats één agenda-event (direct zichtbaar). Caller toetste rate-limit +
    valideerde via ``EventForm``. Defensieve caps spiegelen de kolomlengtes."""
    post = Post(
        added_by_id=member.id,
        kind=PostKind.event,
        title=(title or "").strip()[:200],
        description=(description or None),
        url=(url or None),
        frequency=frequency,
        next_at=next_at,
        cadence_note=(cadence_note or None),
        location=(location or None),
    )
    db.add(post)
    db.flush()
    return post


def create_news(
    db: Session,
    *,
    member: Member,
    title: str,
    url: str,
    role: NewsRole = NewsRole.gedeeld,
    source: str | None = None,
    description: str | None = None,
    published_at: datetime | None = None,
) -> Post:
    """Plaats één nieuwsartikel (direct zichtbaar)."""
    post = Post(
        added_by_id=member.id,
        kind=PostKind.nieuws,
        title=(title or "").strip()[:200],
        description=(description or None),
        url=(url or "").strip()[:500] or None,
        source=(source or None),
        role=role,
        published_at=published_at,
    )
    db.add(post)
    db.flush()
    return post


# --------------------------------------------------------------------------- #
# Weergave                                                                     #
# --------------------------------------------------------------------------- #


def _visible(db: Session, kind: PostKind) -> list[Post]:
    stmt = select(Post).where(Post.kind == kind, Post.hidden.is_(False))
    return list(db.scalars(stmt).all())


def _event_sort_key(post: Post, now: datetime) -> tuple:
    """Aankomend eerst (op ``next_at`` oplopend), dan terugkerend-zonder-datum,
    dan verlopen (op ``next_at`` aflopend). ``created_at`` breekt gelijkspel."""
    created = post.created_at or now
    if post.next_at is not None and post.next_at >= now:
        # bucket 0 — aankomend: vroegste datum bovenaan
        return (0, post.next_at, post.id)
    if post.next_at is None:
        # bucket 1 — teruglopend zonder datum: nieuwste plaatsing bovenaan
        return (1, _neg_dt(created), post.id)
    # bucket 2 — verlopen: meest recent verlopen bovenaan
    return (2, _neg_dt(post.next_at), post.id)


def _neg_dt(value: datetime) -> float:
    """Negatieve timestamp voor 'aflopend' binnen een oplopende sort-tuple."""
    return -value.timestamp()


def list_events(db: Session, *, now: datetime | None = None) -> list[Post]:
    """Zichtbare events, aankomend-eerst (zie ``_event_sort_key``)."""
    now = naive_utc(now or utcnow())
    events = _visible(db, PostKind.event)
    return sorted(events, key=lambda p: _event_sort_key(p, now))


def list_news(db: Session) -> list[Post]:
    """Zichtbaar nieuws, nieuwste publicatie eerst (``published_at`` of
    ``created_at`` als terugval)."""
    items = _visible(db, PostKind.nieuws)
    return sorted(
        items,
        key=lambda p: (_neg_dt(p.published_at or p.created_at), -p.id),
    )


def get_visible(
    db: Session, post_id: int, *, kind: PostKind | None = None
) -> Post | None:
    """Eén zichtbare (niet-verborgen) bijdrage, of ``None``. Optioneel op kind."""
    stmt = select(Post).where(Post.id == post_id, Post.hidden.is_(False))
    if kind is not None:
        stmt = stmt.where(Post.kind == kind)
    return db.scalar(stmt)


# --------------------------------------------------------------------------- #
# Moderatie (admin)                                                           #
# --------------------------------------------------------------------------- #


def set_hidden(
    db: Session,
    post: Post,
    *,
    hidden: bool = True,
    actor: Member | None = None,
) -> Post:
    """Zet (of haal weg) de admin-``hidden``-vlag + schrijf een AuditLog bij
    verbergen (spiegelt ``idea_service.set_hidden``)."""
    post.hidden = hidden
    if hidden:
        db.add(
            AuditLog(
                action=AuditAction.post_hidden,
                actor_member_id=actor.id if actor is not None else None,
                target_member_id=post.added_by_id,
                detail=f"post#{post.id} ({post.kind.value}) hidden",
            )
        )
    db.flush()
    return post
