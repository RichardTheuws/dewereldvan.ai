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
