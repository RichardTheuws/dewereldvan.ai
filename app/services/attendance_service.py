"""Attendance-service — RSVP op agenda-events (de sociale laag).

Eén rol per lid per event (``set_role`` upsert't; ``clear`` haalt 'm weg). De
weergave-kant levert een ``AttendanceSummary`` per event — tellingen + de namen
van organisatoren/sprekers (gelinkt naar hun publieke profiel = graaf-knoop) + de
eigen keuze van de kijker (voor de ``:checked``-stijl). ``summaries`` doet dat voor
een hele lijst events in **één** query (geen N+1).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    EventAttendance,
    EventAttendanceRole,
    Member,
    Post,
    Visibility,
)

__all__ = [
    "Attendee",
    "AttendanceSummary",
    "set_role",
    "clear",
    "summaries",
    "summary_for",
]


@dataclass(frozen=True)
class Attendee:
    """Een betrokken lid voor de weergave: naam + (als z'n profiel publiek is) de
    slug voor de profiel-link. ``slug=None`` → toon alleen de naam (geen link)."""

    name: str
    slug: str | None


@dataclass
class AttendanceSummary:
    """De aanmeld-stand van één event, klaar voor de RSVP-strip."""

    attending: int = 0
    organizing: int = 0
    speaking: int = 0
    organizers: list[Attendee] = field(default_factory=list)
    speakers: list[Attendee] = field(default_factory=list)
    # De rol van de huidige kijker op dit event (of ``None`` als niet/anon).
    viewer_role: str | None = None

    @property
    def total(self) -> int:
        """Iedereen die op welke manier dan ook 'gaat' (aanwezig + org + spreker)."""
        return self.attending + self.organizing + self.speaking

    @property
    def has_anyone(self) -> bool:
        return self.total > 0


# --------------------------------------------------------------------------- #
# Schrijven (upsert / clear)                                                   #
# --------------------------------------------------------------------------- #


def set_role(
    db: Session, *, member: Member, post: Post, role: EventAttendanceRole
) -> EventAttendance:
    """Zet (of wijzig) de rol van ``member`` op ``post``. Eén rij per (event, lid):
    bestaat 'ie al, dan updaten we de rol (geen dubbele rij)."""
    row = db.scalar(
        select(EventAttendance).where(
            EventAttendance.post_id == post.id,
            EventAttendance.member_id == member.id,
        )
    )
    if row is None:
        row = EventAttendance(post_id=post.id, member_id=member.id, role=role)
        db.add(row)
    else:
        row.role = role
    db.flush()
    return row


def clear(db: Session, *, member: Member, post: Post) -> None:
    """Verwijder de aanmelding van ``member`` op ``post`` (idempotent)."""
    db.execute(
        delete(EventAttendance).where(
            EventAttendance.post_id == post.id,
            EventAttendance.member_id == member.id,
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# Weergave (N+1-vrij)                                                          #
# --------------------------------------------------------------------------- #


def _attendee(att: EventAttendance) -> Attendee:
    """Naam (profiel-displaynaam → val terug op lid-naam) + slug als het profiel
    publiek is (dan linkt de naam naar /leden/{slug})."""
    member = att.member
    profile = member.profile if member is not None else None
    name = ""
    if profile is not None and profile.display_name:
        name = profile.display_name
    elif member is not None:
        name = member.name
    slug = None
    if profile is not None and profile.visibility == Visibility.public:
        slug = profile.slug
    return Attendee(name=name, slug=slug)


def summaries(
    db: Session, posts: list[Post], *, viewer: Member | None = None
) -> dict[int, AttendanceSummary]:
    """Aanmeld-stand per event-id voor een lijst events — in één query (geen N+1).
    Elke ``post`` zonder aanmeldingen krijgt een lege summary."""
    out: dict[int, AttendanceSummary] = {p.id: AttendanceSummary() for p in posts}
    post_ids = list(out.keys())
    if not post_ids:
        return out
    rows = db.scalars(
        select(EventAttendance)
        .where(EventAttendance.post_id.in_(post_ids))
        .options(joinedload(EventAttendance.member).joinedload(Member.profile))
        .order_by(EventAttendance.created_at)
    ).all()
    viewer_id = viewer.id if viewer is not None else None
    for r in rows:
        s = out.get(r.post_id)
        if s is None:
            continue
        if r.role == EventAttendanceRole.organizing:
            s.organizing += 1
            s.organizers.append(_attendee(r))
        elif r.role == EventAttendanceRole.speaking:
            s.speaking += 1
            s.speakers.append(_attendee(r))
        else:  # attending
            s.attending += 1
        if viewer_id is not None and r.member_id == viewer_id:
            s.viewer_role = r.role.value
    return out


def summary_for(
    db: Session, post: Post, *, viewer: Member | None = None
) -> AttendanceSummary:
    """De aanmeld-stand van één event (voor de htmx-swap na een RSVP-actie)."""
    return summaries(db, [post], viewer=viewer)[post.id]
