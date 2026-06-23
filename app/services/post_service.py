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

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AuditAction,
    AuditLog,
    EventCategory,
    EventFrequency,
    Member,
    NewsRole,
    Post,
    PostKind,
    PostReviewState,
    PostSourceKind,
)
from app.security import naive_utc, utcnow

__all__ = [
    "PostRateLimited",
    "check_post_rate_limit",
    "create_event",
    "create_news",
    "create_curated_news",
    "create_curated_event",
    "list_events",
    "category_options",
    "list_news",
    "list_briefing",
    "list_pending_review",
    "list_pending_events",
    "approve_news",
    "reject_news",
    "approve_event",
    "reject_event",
    "get_visible",
    "set_hidden",
    "iso_week_anchor",
    "relatieve_tijd",
    "nl_datum",
    "NewsBriefing",
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
    category: EventCategory = EventCategory.meetup,
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
        category=category,
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
    """Publiek zichtbare bijdragen: niet-verborgen ÉN ``review_state == live``.

    De ``live``-poort is de mens-in-de-lus-grens: AI-gecureerde kandidaten
    (``pending_review``) en geweigerde items (``rejected``) komen hier NOOIT door —
    niet op /nieuws, niet in de briefing-strip. Events staan default op ``live``,
    dus deze filter wijzigt het agenda-gedrag niet."""
    stmt = select(Post).where(
        Post.kind == kind,
        Post.hidden.is_(False),
        Post.review_state == PostReviewState.live,
    )
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


def list_events(
    db: Session,
    *,
    category: str | None = None,
    now: datetime | None = None,
) -> list[Post]:
    """Zichtbare events, aankomend-eerst (zie ``_event_sort_key``). Optioneel
    gefilterd op ``category`` — een onbekende/lege waarde negeert de filter
    (alle events)."""
    now = naive_utc(now or utcnow())
    events = _visible(db, PostKind.event)
    cat = (category or "").strip()
    if cat in {c.value for c in EventCategory}:
        events = [p for p in events if p.category is not None and p.category.value == cat]
    return sorted(events, key=lambda p: _event_sort_key(p, now))


def category_options() -> list[tuple[str, str]]:
    """(slug, label) voor de categorie-filterchips + de event-form-select op
    /agenda. Label = de waarde met hoofdletter (de enum-waarden zijn al leesbaar
    Nederlands/Engels-courant)."""
    return [(c.value, c.value.capitalize()) for c in EventCategory]


def list_news(db: Session) -> list[Post]:
    """Zichtbaar nieuws (alle weken samen), nieuwste publicatie eerst
    (``published_at`` of ``created_at`` als terugval)."""
    items = _visible(db, PostKind.nieuws)
    return sorted(
        items,
        key=lambda p: (_neg_dt(p.published_at or p.created_at), -p.id),
    )


def iso_week_anchor(value: date | datetime | None = None) -> date:
    """De maandag van de ISO-week van ``value`` (default: nu) — het ankerpunt voor
    ``briefing_week``. Items met dit anker horen bij "Deze week"."""
    if value is None:
        value = naive_utc(utcnow())
    d = value.date() if isinstance(value, datetime) else value
    return d - timedelta(days=d.weekday())


@dataclass(frozen=True)
class NewsBriefing:
    """Het gesplitste nieuws: de briefing van deze week + het doorlopende archief."""

    briefing_this_week: list[Post]
    archief: list[Post]


def list_briefing(db: Session, *, now: datetime | None = None) -> NewsBriefing:
    """Splits het zichtbare nieuws in "Deze week" (``briefing_week`` == lopende
    ISO-week) en het archief (al het overige zichtbare nieuws). Beide nieuwste-
    eerst gesorteerd (``published_at`` → ``created_at`` als terugval)."""
    this_week = iso_week_anchor(now or naive_utc(utcnow()))
    items = list_news(db)  # al gesorteerd + alleen live/zichtbaar
    briefing = [p for p in items if p.briefing_week == this_week]
    archief = [p for p in items if p.briefing_week != this_week]
    return NewsBriefing(briefing_this_week=briefing, archief=archief)


# --------------------------------------------------------------------------- #
# AI-curatie ("De Briefing") — voorstellen + mens-in-de-lus-poort             #
# --------------------------------------------------------------------------- #


def list_pending_review(db: Session) -> list[Post]:
    """De admin-shortlist: AI-gecureerde nieuws-kandidaten die op goedkeuring
    wachten (``review_state == pending_review``). Hoogste relevantie eerst, dan
    nieuwste. Alleen deze staat — ``live``/``rejected`` horen er niet bij."""
    stmt = select(Post).where(
        Post.kind == PostKind.nieuws,
        Post.review_state == PostReviewState.pending_review,
    )
    items = list(db.scalars(stmt).all())
    return sorted(
        items,
        key=lambda p: (-(p.ai_relevance or 0), _neg_dt(p.created_at), -p.id),
    )


def create_curated_news(
    db: Session,
    *,
    title: str,
    url: str,
    ai_take: str | None = None,
    ai_relevance: int | None = None,
    source: str | None = None,
    added_by: Member | None = None,
    briefing_week: date | None = None,
    now: datetime | None = None,
) -> Post:
    """Maak één AI-gecureerd nieuws-VOORSTEL (door de wekelijkse curatie-job).

    MENS-IN-DE-LUS-POORT: dit item start ALTIJD ``pending_review`` —
    nooit ``live``. Het verschijnt pas publiek nadat een admin het goedkeurt.

    Idempotent op ``url``: een herhaalde curatie-run (zelfde artikel) maakt GEEN
    duplicaat — het bestaande nieuws-item (in welke staat dan ook) wordt
    teruggegeven. De job flusht/commit zelf."""
    clean_url = (url or "").strip()[:500]
    if clean_url:
        existing = db.scalar(
            select(Post).where(
                Post.kind == PostKind.nieuws,
                Post.url == clean_url,
            )
        )
        if existing is not None:
            return existing  # dedup: geen dubbele kandidaat

    week = briefing_week or iso_week_anchor(now or naive_utc(utcnow()))
    post = Post(
        added_by_id=added_by.id if added_by is not None else None,
        kind=PostKind.nieuws,
        title=(title or "").strip()[:200],
        url=clean_url or None,
        source=(source or None),
        role=NewsRole.gedeeld,
        # De poort: een voorstel, geen publicatie.
        review_state=PostReviewState.pending_review,
        source_kind=PostSourceKind.ai_curated,
        ai_take=(ai_take.strip()[:600] if ai_take else None),
        ai_relevance=ai_relevance,
        briefing_week=week,
    )
    db.add(post)
    db.flush()
    return post


def _coerce_category(value: object) -> EventCategory:
    try:
        return EventCategory((value or "").strip()) if not isinstance(value, EventCategory) else value
    except ValueError:
        return EventCategory.meetup


def _coerce_frequency(value: object) -> EventFrequency:
    try:
        return EventFrequency((value or "").strip()) if not isinstance(value, EventFrequency) else value
    except ValueError:
        return EventFrequency.eenmalig


def create_curated_event(
    db: Session,
    *,
    title: str,
    url: str,
    category: object = EventCategory.meetup,
    frequency: object = EventFrequency.eenmalig,
    confidence: int | None = None,
    live: bool = False,
    next_at: datetime | None = None,
    location: str | None = None,
    cadence_note: str | None = None,
    description: str | None = None,
    source: str | None = None,
) -> Post:
    """Maak één AI-gecureerd agenda-event (door de wekelijkse curatie-job).

    AUTO-KEUR-POORT: ``live=True`` (alleen als de job het zeker genoeg vond —
    ``event_curation_service.auto_approvable``) → direct publiek. Anders
    ``pending_review`` (admin-queue, twijfel). NOOIT silent-publish bij twijfel.

    Idempotent op ``url``: een herhaalde run (zelfde event-pagina) maakt GEEN
    duplicaat — het bestaande event (in welke staat dan ook) wordt teruggegeven."""
    clean_url = (url or "").strip()[:500]
    if clean_url:
        existing = db.scalar(
            select(Post).where(Post.kind == PostKind.event, Post.url == clean_url)
        )
        if existing is not None:
            return existing  # dedup: geen dubbel event

    post = Post(
        added_by_id=None,
        kind=PostKind.event,
        title=(title or "").strip()[:200],
        url=clean_url or None,
        description=(description or None),
        category=_coerce_category(category),
        frequency=_coerce_frequency(frequency),
        next_at=next_at,
        location=(location or None),
        cadence_note=(cadence_note or None),
        source=(source or None),
        review_state=PostReviewState.live if live else PostReviewState.pending_review,
        source_kind=PostSourceKind.ai_curated,
        ai_relevance=confidence,
    )
    db.add(post)
    db.flush()
    return post


def list_pending_events(db: Session) -> list[Post]:
    """De admin-shortlist voor de agenda: AI-gecureerde event-kandidaten die de
    auto-keur-drempel niet haalden (``review_state == pending_review``). Hoogste
    confidence eerst, dan aankomende datum, dan nieuwste."""
    stmt = select(Post).where(
        Post.kind == PostKind.event,
        Post.review_state == PostReviewState.pending_review,
    )
    items = list(db.scalars(stmt).all())
    return sorted(
        items,
        key=lambda p: (
            -(p.ai_relevance or 0),
            p.next_at or datetime.max,
            _neg_dt(p.created_at),
            -p.id,
        ),
    )


def approve_news(db: Session, post: Post, *, actor: Member | None = None) -> Post:
    """Keur een AI-kandidaat goed → ``live`` (publiek zichtbaar) + AuditLog.
    Spiegelt ``set_hidden``/``admin_hide``: de transitie is de enige plek waar een
    voorstel publiek wordt — bewust één expliciete, geauditte stap."""
    post.review_state = PostReviewState.live
    db.add(
        AuditLog(
            action=AuditAction.news_approved,
            actor_member_id=actor.id if actor is not None else None,
            target_member_id=post.added_by_id,
            detail=f"post#{post.id} (nieuws) approved -> live",
        )
    )
    db.flush()
    return post


def reject_news(db: Session, post: Post, *, actor: Member | None = None) -> Post:
    """Weiger een AI-kandidaat → ``rejected`` (blijft uit de publieke lijst) +
    AuditLog. We verwijderen niet (dedup-context + meet de goedkeur-ratio)."""
    post.review_state = PostReviewState.rejected
    db.add(
        AuditLog(
            action=AuditAction.news_rejected,
            actor_member_id=actor.id if actor is not None else None,
            target_member_id=post.added_by_id,
            detail=f"post#{post.id} (nieuws) rejected",
        )
    )
    db.flush()
    return post


def approve_event(db: Session, post: Post, *, actor: Member | None = None) -> Post:
    """Keur een AI-event-kandidaat goed → ``live`` (publiek op de agenda) +
    AuditLog. Spiegelt ``approve_news`` (de enige plek waar een twijfel-voorstel
    publiek wordt)."""
    post.review_state = PostReviewState.live
    db.add(
        AuditLog(
            action=AuditAction.event_approved,
            actor_member_id=actor.id if actor is not None else None,
            target_member_id=post.added_by_id,
            detail=f"post#{post.id} (event) approved -> live",
        )
    )
    db.flush()
    return post


def reject_event(db: Session, post: Post, *, actor: Member | None = None) -> Post:
    """Weiger een AI-event-kandidaat → ``rejected`` (blijft uit de agenda) +
    AuditLog. We verwijderen niet (dedup-context + meet de goedkeur-ratio)."""
    post.review_state = PostReviewState.rejected
    db.add(
        AuditLog(
            action=AuditAction.event_rejected,
            actor_member_id=actor.id if actor is not None else None,
            target_member_id=post.added_by_id,
            detail=f"post#{post.id} (event) rejected",
        )
    )
    db.flush()
    return post


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
