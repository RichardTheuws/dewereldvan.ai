"""Ideeen-service (E2) — CRUD, stemmen (uniek), moderatie en promotie.

Verantwoordelijkheden:

1. **Indienen** (``create``) — één ``Idea``-rij per lid, met per-lid rate-limit in
   een glijdend uur-venster (``magic_link._recent_count``-patroon).
2. **Stemmen** (``vote``) — één upvote per lid per idee. De uniekheid is HARD via
   de DB-constraint ``uq_idea_vote(idea_id, member_id)``; een dubbele stem raakt
   een ``IntegrityError`` die we netjes als "al gestemd" afhandelen (rollback van
   de savepoint, geen 500, geen dubbele telling).
3. **Weergave** (``list_visible`` / ``vote_counts`` / ``voted_idea_ids``) — de
   zichtbare lijst (niet ``hidden``) met stemtotalen en of het huidige lid al
   stemde, voor de kosmische lijst + stemknop-swap.
4. **Moderatie** (``set_hidden`` / ``set_status``) — admin verbergt of zet status.
5. **Promotie** (``promote``) — maak een ``RoadmapItem`` met ``linked_idea_id``,
   zet de idee-status op ``gepland`` en schrijf een ``idea_promoted``-AuditLog.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AuditAction,
    AuditLog,
    Idea,
    IdeaStatus,
    IdeaVote,
    Member,
    RoadmapItem,
    RoadmapStatus,
)
from app.security import naive_utc, utcnow

__all__ = [
    "IdeaRateLimited",
    "VoteResult",
    "check_idea_rate_limit",
    "create",
    "list_visible",
    "get_visible",
    "vote_counts",
    "voted_idea_ids",
    "vote",
    "set_hidden",
    "set_status",
    "promote",
]


class IdeaRateLimited(RuntimeError):
    """Het lid overschreed de idee-indien-rate-limit binnen het uur-venster."""


# --------------------------------------------------------------------------- #
# Rate-limit (per lid, glijdend uur-venster)                                  #
# --------------------------------------------------------------------------- #


def _recent_idea_count(db: Session, member_id: int, now: datetime) -> int:
    window_start = naive_utc(now) - timedelta(hours=1)
    return (
        db.scalar(
            select(func.count())
            .select_from(Idea)
            .where(
                Idea.member_id == member_id,
                Idea.created_at >= window_start,
            )
        )
        or 0
    )


def check_idea_rate_limit(
    db: Session,
    member: Member,
    *,
    now: datetime | None = None,
) -> None:
    """Raise ``IdeaRateLimited`` als het lid het uur-budget overschreed."""
    now = now or utcnow()
    if _recent_idea_count(db, member.id, now) >= settings.rate_limit_idea_per_hour:
        raise IdeaRateLimited()


# --------------------------------------------------------------------------- #
# Indienen                                                                    #
# --------------------------------------------------------------------------- #


def create(
    db: Session,
    *,
    member: Member,
    title: str,
    body: str,
) -> Idea:
    """Dien één idee in (status ``open``) en geef de rij terug.

    De caller heeft de rate-limit al via ``check_idea_rate_limit`` getoetst en de
    input via ``IdeaForm`` gevalideerd. Defensieve caps spiegelen de kolomlengtes.
    """
    title = (title or "").strip()[:160]
    body = (body or "").strip()[:4000]
    idea = Idea(
        member_id=member.id,
        title=title,
        body=body,
        status=IdeaStatus.open,
    )
    db.add(idea)
    db.flush()
    return idea


# --------------------------------------------------------------------------- #
# Weergave                                                                    #
# --------------------------------------------------------------------------- #


def list_visible(db: Session) -> list[Idea]:
    """Zichtbare ideeen (niet ``hidden``), meest gestemde eerst, dan nieuwste.

    De stemtelling-sortering gebeurt met een left-join + ``count`` zodat ideeen
    zonder stemmen (telling 0) gewoon meedoen.
    """
    vote_count = func.count(IdeaVote.id)
    stmt = (
        select(Idea)
        .outerjoin(IdeaVote, IdeaVote.idea_id == Idea.id)
        .where(Idea.hidden.is_(False))
        .group_by(Idea.id)
        .order_by(vote_count.desc(), Idea.created_at.desc(), Idea.id.desc())
    )
    return list(db.scalars(stmt).all())


def get_visible(db: Session, idea_id: int) -> Idea | None:
    """Eén zichtbaar (niet-verborgen) idee, of ``None``."""
    return db.scalar(
        select(Idea).where(Idea.id == idea_id, Idea.hidden.is_(False))
    )


def vote_counts(db: Session, idea_ids: list[int] | None = None) -> dict[int, int]:
    """Map ``idea_id -> stemtelling``. Zonder ``idea_ids`` voor alle ideeen."""
    stmt = select(IdeaVote.idea_id, func.count(IdeaVote.id)).group_by(
        IdeaVote.idea_id
    )
    if idea_ids is not None:
        if not idea_ids:
            return {}
        stmt = stmt.where(IdeaVote.idea_id.in_(idea_ids))
    return {idea_id: count for idea_id, count in db.execute(stmt).all()}


def count_votes(db: Session, idea_id: int) -> int:
    """Stemtelling voor één idee."""
    return (
        db.scalar(
            select(func.count())
            .select_from(IdeaVote)
            .where(IdeaVote.idea_id == idea_id)
        )
        or 0
    )


def voted_idea_ids(db: Session, member: Member, idea_ids: list[int] | None = None) -> set[int]:
    """Set van idee-ids waarop dit lid al stemde (voor de stemknop-staat)."""
    stmt = select(IdeaVote.idea_id).where(IdeaVote.member_id == member.id)
    if idea_ids is not None:
        if not idea_ids:
            return set()
        stmt = stmt.where(IdeaVote.idea_id.in_(idea_ids))
    return set(db.scalars(stmt).all())


def has_voted(db: Session, member: Member, idea_id: int) -> bool:
    """True als dit lid al op dit idee stemde."""
    return (
        db.scalar(
            select(IdeaVote.id).where(
                IdeaVote.idea_id == idea_id, IdeaVote.member_id == member.id
            )
        )
        is not None
    )


# --------------------------------------------------------------------------- #
# Stemmen (uniek — IntegrityError netjes afgevangen)                          #
# --------------------------------------------------------------------------- #


class VoteResult:
    """Uitkomst van een stem-poging: actuele telling + of er nu gestemd is.

    ``created`` is ``False`` als het lid al gestemd had (idempotent, geen
    dubbele telling); ``count`` is in beide gevallen de actuele stemtelling.
    """

    __slots__ = ("count", "created")

    def __init__(self, count: int, created: bool) -> None:
        self.count = count
        self.created = created


def vote(db: Session, idea: Idea, member: Member) -> VoteResult:
    """Voeg één upvote toe; idempotent bij een dubbele stem.

    De uniekheid is HARD via ``uq_idea_vote``. We proberen de stem in een nested
    transaction (savepoint); een ``IntegrityError`` (race / dubbele submit) wordt
    naar dat savepoint teruggerold zodat de buitenste sessie bruikbaar blijft, en
    behandeld als "al gestemd" — geen 500, geen dubbele telling.
    """
    created = False
    try:
        with db.begin_nested():
            db.add(IdeaVote(idea_id=idea.id, member_id=member.id))
            db.flush()
        created = True
    except IntegrityError:
        # Dubbele stem (UNIQUE-schending): de savepoint is teruggerold; behandel
        # als reeds gestemd. De buitenste sessie blijft intact.
        created = False
    return VoteResult(count=count_votes(db, idea.id), created=created)


# --------------------------------------------------------------------------- #
# Moderatie (admin)                                                           #
# --------------------------------------------------------------------------- #


def set_hidden(
    db: Session,
    idea: Idea,
    *,
    hidden: bool = True,
    actor: Member | None = None,
) -> Idea:
    """Zet (of haal weg) de admin-``hidden``-vlag + schrijf een AuditLog."""
    idea.hidden = hidden
    if hidden:
        db.add(
            AuditLog(
                action=AuditAction.idea_hidden,
                actor_member_id=actor.id if actor is not None else None,
                target_member_id=idea.member_id,
                detail=f"idea#{idea.id} hidden",
            )
        )
    db.flush()
    return idea


def set_status(db: Session, idea: Idea, status: IdeaStatus) -> Idea:
    """Zet de idee-status (open/gepland/gedaan/afgewezen)."""
    idea.status = status
    db.flush()
    return idea


# --------------------------------------------------------------------------- #
# Promotie naar de roadmap                                                     #
# --------------------------------------------------------------------------- #


def promote(
    db: Session,
    idea: Idea,
    *,
    actor: Member | None = None,
    phase: str = "Volgende",
) -> RoadmapItem:
    """Promoot een idee naar een ``RoadmapItem`` en zet de idee-status op ``gepland``.

    Het nieuwe roadmap-item krijgt ``linked_idea_id == idea.id`` (de FK is
    ``SET NULL`` zodat een later verwijderd idee het item laat staan), status
    ``overwegen`` en een ``position`` achteraan binnen de gekozen ``phase``. Er
    wordt exact één ``idea_promoted``-AuditLog geschreven.

    Idempotent: bestaat er al een ``RoadmapItem`` voor dit idee (dubbele klik /
    dubbele submit), dan geven we dat bestaande item terug zonder een tweede
    roadmap-rij of audit-rij te maken.
    """
    existing = db.scalar(
        select(RoadmapItem).where(RoadmapItem.linked_idea_id == idea.id)
    )
    if existing is not None:
        return existing

    next_position = (
        db.scalar(
            select(func.coalesce(func.max(RoadmapItem.position), -1) + 1).where(
                RoadmapItem.phase == phase
            )
        )
        or 0
    )
    item = RoadmapItem(
        title=idea.title,
        description=idea.body,
        status=RoadmapStatus.overwegen,
        phase=phase,
        position=next_position,
        linked_idea_id=idea.id,
    )
    db.add(item)
    idea.status = IdeaStatus.gepland
    db.add(
        AuditLog(
            action=AuditAction.idea_promoted,
            actor_member_id=actor.id if actor is not None else None,
            target_member_id=idea.member_id,
            detail=f"idea#{idea.id} -> roadmap",
        )
    )
    db.flush()
    return item
