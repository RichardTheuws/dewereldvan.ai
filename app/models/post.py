"""Post model — één holistische community-bijdrage (agenda + nieuws + later meer).

Elk goedgekeurd lid publiceert direct (geen goedkeuringswachtrij); admin kan een
bijdrage **verbergen** (``hidden``, spiegelt ``idea.hidden``). ``kind`` bepaalt
welke type-specifieke velden meedoen en op welke pagina de bijdrage leeft:

- ``event``  → ``frequency`` / ``next_at`` / ``cadence_note`` / ``location`` (/agenda)
- ``nieuws`` → ``source`` / ``role`` / ``published_at`` (/nieuws)

De gedeelde velden (``title`` / ``description`` / ``url``) gelden voor beide. Nieuwe
contenttypes ("etc") worden een extra ``PostKind``-waarde + een handvol nullable
kolommen — geen tweede tabel/router/stack.

``added_by_id`` is **SET NULL** (anders dan ``idea.member_id`` → CASCADE): een
community-meetup of gedeeld artikel houdt waarde voor de groep, ook als de
toevoeger zijn account wist. Admin/seed mag ``NULL`` (geen toevoeger).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    EventFrequency,
    NewsRole,
    PostKind,
    PostReviewState,
    PostSourceKind,
)

if TYPE_CHECKING:
    from app.models.member import Member


class Post(Base):
    __tablename__ = "post"

    id: Mapped[int] = mapped_column(primary_key=True)
    # SET NULL: een gewist account laat de bijdrage staan (community-waarde);
    # nullable zodat admin/seed zonder toevoeger mag plaatsen.
    added_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("member.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kind: Mapped[PostKind] = mapped_column(
        SQLEnum(PostKind, name="post_kind", native_enum=False),
        nullable=False,
        index=True,
    )

    # --- gedeelde velden ------------------------------------------------------
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # --- event-specifiek (kind == event) -------------------------------------
    frequency: Mapped[EventFrequency | None] = mapped_column(
        SQLEnum(EventFrequency, name="event_frequency", native_enum=False),
        nullable=True,
    )
    next_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cadence_note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # --- nieuws-specifiek (kind == nieuws) -----------------------------------
    source: Mapped[str | None] = mapped_column(String(160), nullable=True)
    role: Mapped[NewsRole | None] = mapped_column(
        SQLEnum(NewsRole, name="news_role", native_enum=False), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- "De Briefing" (doc 02 §4) — AUGMENT, vijf nullable kolommen ----------
    # Lid-bijdragen blijven ``live``/``member`` (huidige flow ongewijzigd); de
    # wekelijkse AI-curatie-job zet kandidaten op ``pending_review``/``ai_curated``
    # — NOOIT live. Een admin keurt de shortlist met één klik goed.
    review_state: Mapped[PostReviewState] = mapped_column(
        SQLEnum(PostReviewState, name="post_review_state", native_enum=False),
        nullable=False,
        default=PostReviewState.live,
        server_default=PostReviewState.live.value,
        index=True,
    )
    source_kind: Mapped[PostSourceKind] = mapped_column(
        SQLEnum(PostSourceKind, name="post_source_kind", native_enum=False),
        nullable=False,
        default=PostSourceKind.member,
        server_default=PostSourceKind.member.value,
    )
    ai_relevance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_take: Mapped[str | None] = mapped_column(Text, nullable=True)
    briefing_week: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    added_by: Mapped[Member | None] = relationship()
