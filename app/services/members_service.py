"""Ledenpagina-service (L2) — publieke profielen ophalen + filteren/zoeken.

De publieke constellatie op ``/leden`` toont uitsluitend profielen die voor een
anonieme bezoeker zichtbaar zijn: ``visibility=public`` ÉN een goedgekeurde
eigenaar (geschorst/afgewezen → offline, AVG). Dit spiegelt exact
``visibility.can_view(profile, viewer=None)`` / ``is_noindex`` — één poort.

Filters (alle server-side, optioneel, combineerbaar):
- ``tag``   : profielen met een tag waarvan naam/slug op de term matcht.
- ``maakt`` : term in ``makes_summary`` of een offering-``title``.
- ``zoekt`` : term in een need-``title``.
- ``tool``  : profielen die een tool gebruiken waarvan naam/slug op de term matcht.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Member,
    MemberStatus,
    Need,
    Offering,
    Profile,
    Tag,
    Tool,
    Visibility,
    profile_tag,
    profile_tool,
)

__all__ = ["list_public_profiles", "filter_vocabulary"]


def filter_vocabulary(db: Session) -> dict[str, list[str]]:
    """Distinct tag- en toolnamen van publieke profielen (filter-autocomplete).

    Herbruikt de publieke-poort (``list_public_profiles`` eager-load't tags/tools),
    dus alleen wat een bezoeker daadwerkelijk kan filteren komt in de suggesties —
    geen lege/besloten termen. Eén query, in-memory ontdubbeld + gesorteerd."""
    profiles = list_public_profiles(db)
    tags = sorted({t.name for p in profiles for t in p.tags}, key=str.lower)
    tools = sorted({t.name for p in profiles for t in p.tools}, key=str.lower)
    return {"tags": tags, "tools": tools}


def _public_base():
    """Selectie-basis: alleen publieke profielen van goedgekeurde leden.

    Identiek aan ``can_view(profile, viewer=None)``: ``visibility=public`` +
    eigenaar ``status=approved``. Gebruikt door zowel de ledenpagina als
    (indirect) door de sitemap-poort, zodat besloten/geschorst nooit lekt.
    """
    return (
        select(Profile)
        .join(Member, Profile.member_id == Member.id)
        .where(
            Profile.visibility == Visibility.public,
            Member.status == MemberStatus.approved,
        )
    )


def list_public_profiles(
    db: Session,
    *,
    tag: str | None = None,
    maakt: str | None = None,
    zoekt: str | None = None,
    tool: str | None = None,
) -> list[Profile]:
    """Publieke, goedgekeurde profielen voor de constellatie, optioneel gefilterd.

    Lege/whitespace filterwaarden worden genegeerd. Meerdere filters combineren
    met AND. Resultaat is op ``display_name`` gesorteerd en eager-load't de
    relaties die de kaart-/detailtemplate nodig heeft (tags/offerings/needs/
    member) zodat de render geen N+1 doet.
    """
    stmt = _public_base()

    tag_q = (tag or "").strip()
    if tag_q:
        like = f"%{tag_q.lower()}%"
        stmt = (
            stmt.join(profile_tag, profile_tag.c.profile_id == Profile.id)
            .join(Tag, Tag.id == profile_tag.c.tag_id)
            .where(or_(Tag.slug.ilike(like), Tag.name.ilike(like)))
        )

    maakt_q = (maakt or "").strip()
    if maakt_q:
        like = f"%{maakt_q}%"
        offering_match = select(Offering.id).where(
            Offering.profile_id == Profile.id,
            Offering.title.ilike(like),
        )
        stmt = stmt.where(
            or_(
                Profile.makes_summary.ilike(like),
                offering_match.exists(),
            )
        )

    zoekt_q = (zoekt or "").strip()
    if zoekt_q:
        like = f"%{zoekt_q}%"
        need_match = select(Need.id).where(
            Need.profile_id == Profile.id,
            Need.title.ilike(like),
        )
        stmt = stmt.where(need_match.exists())

    tool_q = (tool or "").strip()
    if tool_q:
        # EXISTS-subquery (geen join) zodat de tool-filter de tag-join + distinct
        # niet kruist; naam/slug-match, lowercased like (spiegelt de tag-filter).
        like = f"%{tool_q.lower()}%"
        tool_match = (
            select(profile_tool.c.profile_id)
            .join(Tool, Tool.id == profile_tool.c.tool_id)
            .where(
                profile_tool.c.profile_id == Profile.id,
                or_(Tool.slug.ilike(like), Tool.name.ilike(like)),
            )
        )
        stmt = stmt.where(tool_match.exists())

    stmt = (
        stmt.distinct()
        .order_by(Profile.display_name.asc(), Profile.id.asc())
        .options(
            selectinload(Profile.tags),
            selectinload(Profile.tools),
            selectinload(Profile.offerings),
            selectinload(Profile.needs),
            selectinload(Profile.member),
        )
    )
    return list(db.scalars(stmt).unique().all())
