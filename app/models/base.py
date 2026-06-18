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
