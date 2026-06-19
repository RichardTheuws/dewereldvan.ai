"""Declarative base, timestamp mixin, and shared enums.

Enum storage convention: every enum is persisted with
``SQLEnum(XEnum, name="...", native_enum=False)`` so it is emitted as
VARCHAR + CHECK. This keeps the schema identical on Postgres (prod) and
SQLite (tests). native_enum=False is non-negotiable for test parity.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MemberStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    suspended = "suspended"
    rejected = "rejected"


class MemberRole(str, enum.Enum):
    member = "member"
    admin = "admin"


class Visibility(str, enum.Enum):
    members = "members"  # default — alleen ingelogde leden
    public = "public"  # openbare URL + indexeerbaar


class AuditAction(str, enum.Enum):
    member_approved = "member_approved"
    member_rejected = "member_rejected"
    member_suspended = "member_suspended"
    visibility_changed = "visibility_changed"
    # Foto-upload spoor (AVG) + grondslag voor de upload-rate-limit (per lid,
    # glijdend uur-venster). VARCHAR-enum → additieve waarde, geen migratie nodig.
    photo_uploaded = "photo_uploaded"
    # Ervaring-laag moderatie (E1-E3). VARCHAR-enum → additieve waarden, geen
    # migratie nodig (de audit_action-kolom is geen native enum).
    feedback_hidden = "feedback_hidden"
    idea_hidden = "idea_hidden"
    idea_promoted = "idea_promoted"
    # Groep-invite-link (PRD-verificatie-links §0). VARCHAR-enum → additieve
    # waarden, geen migratie nodig (de audit_action-kolom is geen native enum).
    invite_generated = "invite_generated"  # admin genereert/roteert de link
    invite_registration = "invite_registration"  # lid komt binnen via de link
    # AVG: een lid wist zijn eigen account + profiel volledig (één-druk-knop).
    # We bewaren één PII-loze audit-rij van de wissing zelf (actor/target genuld,
    # geen e-mail/naam). VARCHAR-enum → additieve waarde, geen migratie nodig.
    member_deleted = "member_deleted"
    # Agenda/nieuws-moderatie (Post). Een lid plaatst direct zichtbaar; admin kan
    # verbergen. VARCHAR-enum → additieve waarde, geen migratie nodig.
    post_hidden = "post_hidden"


class ProfileEmphasis(str, enum.Enum):
    """Layout-prominentie van een profiel/ledenkaart (PRD L1).

    Gevraagd in de AI-bouwflow én bewerkbaar; stuurt welke laag groot getoond
    wordt op de profielpagina en de ledenkaart.
    """

    person = "person"  # foto/headline/bio groot, projecten secundair
    projects = "projects"  # projectkaarten-met-beeld groot, persoon compact
    balanced = "balanced"  # gelijk (default)


class ProfileLinkKind(str, enum.Enum):
    affiliation = "affiliation"  # rol/affiliatie ("verantwoordelijk voor X")
    build = "build"  # iets dat het lid bouwt
    other = "other"


class IdeaStatus(str, enum.Enum):
    """Status van een ideeenbus-idee (E2). Langste waarde 'afgewezen' = 9 →
    de DDL-kolom is ``String(length=9)`` (zie 0005_ervaring)."""

    open = "open"
    gepland = "gepland"
    gedaan = "gedaan"
    afgewezen = "afgewezen"


class RoadmapStatus(str, enum.Enum):
    """Status van een roadmap-item (E3). Langste waarde 'overwegen' = 9 →
    de DDL-kolom is ``String(length=9)`` (zie 0005_ervaring)."""

    overwegen = "overwegen"
    gepland = "gepland"
    bezig = "bezig"
    gedaan = "gedaan"


class PostKind(str, enum.Enum):
    """Soort community-bijdrage (``Post``). Eén holistische entiteit voor alles
    wat een lid direct publiceert; ``kind`` stuurt welke velden meedoen en op
    welke pagina (/agenda · /nieuws) de bijdrage leeft. Langste waarde 'nieuws'
    = 6 → de DDL-kolom is ``String(length=6)`` (zie 0010_post)."""

    event = "event"
    nieuws = "nieuws"


class EventFrequency(str, enum.Enum):
    """Cadans van een agenda-event. Voedt de zichtbare frequentie-badge; bewust
    simpel (geen RRULE/iCal). Langste waarde 'tweewekelijks' = 13 → de DDL-kolom
    is ``String(length=13)`` (zie 0010_post)."""

    eenmalig = "eenmalig"
    wekelijks = "wekelijks"
    tweewekelijks = "tweewekelijks"
    maandelijks = "maandelijks"
    doorlopend = "doorlopend"


class NewsRole(str, enum.Enum):
    """Hoe een lid bij een nieuwsartikel betrokken is (kleine rol-badge op de
    nieuwskaart). Langste waarde 'geinterviewd' = 12 → de DDL-kolom is
    ``String(length=12)`` (zie 0010_post)."""

    geschreven = "geschreven"  # zelf geschreven
    geinterviewd = "geinterviewd"  # geïnterviewd / aan het woord
    vermeld = "vermeld"  # genoemd / uitgelicht
    gedeeld = "gedeeld"  # interessant, gewoon gedeeld


class MatchStatus(str, enum.Enum):
    """Status van een match-suggestie (need ↔ offering). ``new`` voedt de push-
    chip; ``dismissed`` blijft sticky; ``acted`` = er is een intro op gestuurd.
    Langste waarde 'dismissed' = 9 → de DDL-kolom is ``String(length=9)``
    (zie 0012_match_suggestion)."""

    new = "new"
    seen = "seen"
    dismissed = "dismissed"
    acted = "acted"
