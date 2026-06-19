"""Connection-service (Tier 1 Fase 2) — persistente intro's + accept/decline.

Verzilvert een match: een lid stelt zich voor (``create_intro``), het andere lid
krijgt een notificatie en accepteert/wijst af. Bij ``accepted`` opent de contact-
poort (``can_view_contact``). Pure DB-logica — de e-mailverzending zit in de router
(die de ``EmailSender``-dependency + ``EmailSendError``-discipline heeft).

Guardrails:
- **Geen self-intro** (from != to) en **geen dubbele**: bestaat er al een pending/
  accepted intro from→to, dan geven we die terug (geen tweede mail, geen spam).
- **Rate-limit** per lid (glijdend uur-venster, spiegelt idea/post).
- Een intro op een match zet ``match.status = acted`` (de match is verzilverd).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ConnectionStatus, MatchStatus, Member
from app.models.connection import Connection
from app.models.match_suggestion import MatchSuggestion
from app.security import naive_utc, utcnow

__all__ = [
    "IntroRateLimited",
    "check_intro_rate_limit",
    "existing_between",
    "create_intro",
    "accept",
    "decline",
    "get",
    "list_incoming",
    "list_outgoing",
    "list_for_member",
    "count_pending_incoming",
    "can_view_contact",
    "counterpart_for_match",
]


class IntroRateLimited(RuntimeError):
    """Het lid overschreed de intro-rate-limit binnen het uur-venster."""


def _recent_intro_count(db: Session, member_id: int, now: datetime) -> int:
    window_start = naive_utc(now) - timedelta(hours=1)
    return (
        db.scalar(
            select(func.count())
            .select_from(Connection)
            .where(
                Connection.from_member_id == member_id,
                Connection.created_at >= window_start,
            )
        )
        or 0
    )


def check_intro_rate_limit(db: Session, member: Member, *, now: datetime | None = None) -> None:
    now = now or utcnow()
    if _recent_intro_count(db, member.id, now) >= settings.rate_limit_intro_per_hour:
        raise IntroRateLimited()


def existing_between(db: Session, from_id: int, to_id: int) -> Connection | None:
    """Een lopende (pending/accepted) intro van ``from`` naar ``to``, of ``None``."""
    return db.scalar(
        select(Connection).where(
            Connection.from_member_id == from_id,
            Connection.to_member_id == to_id,
            Connection.status != ConnectionStatus.declined,
        )
    )


def counterpart_for_match(match: MatchSuggestion, viewer: Member) -> int | None:
    """Wie is de 'andere kant' van een match voor dit lid? De zoeker stelt zich
    voor aan de maker (en omgekeerd). ``None`` als het lid geen partij is."""
    if match.seeker_member_id == viewer.id:
        return match.maker_member_id
    if match.maker_member_id == viewer.id:
        return match.seeker_member_id
    return None


def create_intro(
    db: Session,
    *,
    from_member: Member,
    to_member: Member,
    message: str,
    match: MatchSuggestion | None = None,
) -> Connection:
    """Persisteer een intro (idempotent op een lopende intro). Zet de match op
    ``acted``. De caller toetste rate-limit + verstuurt daarna de mail."""
    existing = existing_between(db, from_member.id, to_member.id)
    if existing is not None:
        return existing
    conn = Connection(
        from_member_id=from_member.id,
        to_member_id=to_member.id,
        match_suggestion_id=match.id if match is not None else None,
        message=(message or "").strip()[:2000],
        status=ConnectionStatus.pending,
    )
    db.add(conn)
    if match is not None:
        match.status = MatchStatus.acted
    db.flush()
    return conn


def accept(db: Session, conn: Connection, *, now: datetime | None = None) -> Connection:
    conn.status = ConnectionStatus.accepted
    conn.responded_at = naive_utc(now or utcnow())
    db.flush()
    return conn


def decline(db: Session, conn: Connection, *, now: datetime | None = None) -> Connection:
    conn.status = ConnectionStatus.declined
    conn.responded_at = naive_utc(now or utcnow())
    db.flush()
    return conn


def get(db: Session, conn_id: int) -> Connection | None:
    return db.get(Connection, conn_id)


def list_incoming(db: Session, member: Member, *, pending_only: bool = False) -> list[Connection]:
    stmt = select(Connection).where(Connection.to_member_id == member.id)
    if pending_only:
        stmt = stmt.where(Connection.status == ConnectionStatus.pending)
    return list(db.scalars(stmt.order_by(Connection.id.desc())))


def list_outgoing(db: Session, member: Member) -> list[Connection]:
    return list(
        db.scalars(
            select(Connection)
            .where(Connection.from_member_id == member.id)
            .order_by(Connection.id.desc())
        )
    )


def list_for_member(db: Session, member: Member) -> list[Connection]:
    """Alle intro's waar dit lid bij betrokken is (in- en uitgaand), nieuwste eerst."""
    return list(
        db.scalars(
            select(Connection)
            .where(
                or_(
                    Connection.from_member_id == member.id,
                    Connection.to_member_id == member.id,
                )
            )
            .order_by(Connection.id.desc())
        )
    )


def count_pending_incoming(db: Session, member: Member) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Connection)
            .where(
                Connection.to_member_id == member.id,
                Connection.status == ConnectionStatus.pending,
            )
        )
        or 0
    )


def can_view_contact(conn: Connection, viewer: Member) -> bool:
    """Contact (e-mail) is pas zichtbaar ná wederzijds akkoord en alleen voor de
    twee betrokkenen (consent-poort)."""
    return conn.status == ConnectionStatus.accepted and viewer.id in (
        conn.from_member_id,
        conn.to_member_id,
    )
