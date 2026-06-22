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

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Member,
    MemberStatus,
    Need,
    Offering,
    OfferingKind,
    Profile,
    Tag,
    Tool,
    Visibility,
    profile_tag,
    profile_tool,
)
from app.security import naive_utc, utcnow

__all__ = [
    "list_public_profiles",
    "filter_vocabulary",
    "select_living_stars",
    "discipline_options",
    "derive_disciplines",
    "infer_desired_kinds",
]

# Discipline (pivot Fase D) = de set werk-soorten die een maker TOONT — afgeleid uit
# de ``kind`` van z'n werk-items (geen apart datamodel). Zo classificeert de showcase
# de maker uit z'n eigen werk: een video → Video-AI, een workshop → Trainer, enz.
# (slug, filter-label (meervoud, voor de chiprij), kaart-label (enkelvoud, per maker),
# offering-kind). Volgorde = de chip-/tag-volgorde.
DISCIPLINES: list[tuple[str, str, str, OfferingKind]] = [
    ("bouwer", "Bouwers", "Bouwer", OfferingKind.project),
    ("video", "Video-AI", "Video-AI", OfferingKind.video),
    ("audio", "Audio-AI", "Audio-AI", OfferingKind.audio),
    ("trainer", "Trainers", "Trainer", OfferingKind.workshop),
    ("publicaties", "Publicaties", "Publicatie", OfferingKind.writing),
]
_DISCIPLINE_KIND: dict[str, OfferingKind] = {s: k for s, _fl, _cl, k in DISCIPLINES}

# Trefwoorden waaruit een VRAAG ("wat ik zoek") een gewenste werk-soort prijsgeeft:
# "ik zoek een workshop over RAG" → workshop, "wie maakt video?" → video. Zero-AI; dit
# voedt de match-kandidaten (discovery-op-discipline), los van de gids-filter (die op de
# getoonde ``kind`` filtert). Alleen hoog-signaal-soorten: ``project`` is de default (zou
# alles matchen) en ``gallery``/``link`` zijn nog niet in gebruik. Alle trefwoorden ≥5
# tekens → prefix-match op een token is veilig (vangt meervoud: video→videos,
# publicatie→publicaties, onderzoek→onderzoeken) zonder korte-woord-valspositieven.
_DESIRED_KIND_KEYWORDS: dict[OfferingKind, tuple[str, ...]] = {
    OfferingKind.workshop: (
        "workshop", "training", "cursus", "masterclass", "webinar", "opleiding",
        "bootcamp", "course",
    ),
    OfferingKind.video: ("video", "showreel", "animatie", "youtube"),
    OfferingKind.audio: ("audio", "podcast", "muziek", "soundtrack"),
    OfferingKind.writing: (
        "artikel", "publicatie", "paper", "onderzoek", "whitepaper", "essay",
        "rapport", "research",
    ),
}


def infer_desired_kinds(*parts: str | None) -> set[OfferingKind]:
    """Welke werk-soort(en) een VRAAG-tekst expliciet vraagt (zero-AI, trefwoord-match).

    Tokeniseert de tekst (lowercased, alnum-woorden) en matcht een werk-soort als een
    token met één van z'n trefwoorden begint. Geeft de matchende ``OfferingKind``-set
    terug (leeg = geen expliciete werk-soort gevraagd → geen discipline-voorrang).
    """
    tokens = {
        "".join(c for c in raw if c.isalnum())
        for part in parts
        for raw in (part or "").lower().replace("/", " ").replace(",", " ").split()
    }
    tokens.discard("")
    desired: set[OfferingKind] = set()
    for kind, keywords in _DESIRED_KIND_KEYWORDS.items():
        if any(tok.startswith(kw) for tok in tokens for kw in keywords):
            desired.add(kind)
    return desired


def discipline_options() -> list[tuple[str, str]]:
    """(slug, meervoud-label) voor de filter-chips op /leden."""
    return [(s, flabel) for s, flabel, _cl, _k in DISCIPLINES]


def derive_disciplines(profile: Profile) -> list[str]:
    """De discipline-labels (enkelvoud) die uit de werk-items van dit profiel blijken
    (vaste volgorde; puur in-memory op de al-geladen ``offerings`` → geen query)."""
    kinds = {o.kind for o in profile.offerings}
    return [clabel for _s, _fl, clabel, k in DISCIPLINES if k in kinds]

# "Pas verschenen" in de constellatie: een maker waarvan de eigenaar (Member) korter
# dan dit aantal dagen geleden is aangemaakt. Zelfde created_at-bron als de
# "nieuwe makers"-chip (nudge_service._count_new_members) → één waarheid.
RECENT_MAKER_DAYS = 7


def select_living_stars(
    profiles: list[Profile],
    *,
    now: datetime | None = None,
    limit: int = 8,
    recent_days: int = RECENT_MAKER_DAYS,
) -> tuple[list[Profile], set[int], int]:
    """Kies tot ``limit`` sterren voor de constellatie, pas-verschenen makers eerst.

    De levende graaf moet laten ZIEN dat de wereld groeide: makers die < ``recent_days``
    dagen geleden verschenen, schuiven naar voren (zodat ze in de zichtbare slice
    vallen en het lid de groei opmerkt). Retourneert ``(stars, new_ids, new_count)``:
    de gekozen profielen, de set Profile-ids bínnen die slice die nieuw zijn (voor de
    "nieuw"-gloed), en het TOTAAL aantal nieuwe makers (ook buiten de slice, voor de
    kop-telling). Puur in-memory op een al-geladen lijst — nul extra query (``member``
    is eager-geladen door ``list_public_profiles``).
    """
    cutoff = naive_utc(now or utcnow()) - timedelta(days=recent_days)

    def _is_new(p: Profile) -> bool:
        m = p.member
        return m is not None and m.created_at is not None and m.created_at >= cutoff

    new = [p for p in profiles if _is_new(p)]
    rest = [p for p in profiles if not _is_new(p)]
    stars = (new + rest)[:limit]
    new_ids = {p.id for p in stars if _is_new(p)}
    return stars, new_ids, len(new)


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
    discipline: str | None = None,
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

    # Discipline (Fase D): mapt op de ``kind`` van de werk-items — een profiel matcht
    # als het ≥1 werk-item van dat soort toont (EXISTS, geen join → geen distinct-kruis).
    discipline_q = (discipline or "").strip().lower()
    if discipline_q in _DISCIPLINE_KIND:
        disc_match = select(Offering.id).where(
            Offering.profile_id == Profile.id,
            Offering.kind == _DISCIPLINE_KIND[discipline_q],
        )
        stmt = stmt.where(disc_match.exists())

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
