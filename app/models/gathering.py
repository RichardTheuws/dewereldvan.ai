"""Samenkomen — de datumprikker als concierge-act (PRD-samenkomen, fase 1).

Vier tabellen, alle dialect-neutraal (VARCHAR + CHECK voor de enums, spiegelt
``event_attendance``):

- ``Gathering``       — de prikker zelf (maker, titel, plek-hint, interesse-grond).
- ``GatheringDate``   — één kandidaat-datum per rij (meerdere per prikker).
- ``GatheringVote``   — één stem per (datum-optie, lid); ``UniqueConstraint`` →
  her-stemmen is een update (race-veilig via savepoint, recept ``idea_service.vote``).
- ``GatheringInvite`` — wie is expliciet uitgenodigd (voor het seintje + de chip).

Wint een datum, dan klapt de prikker samen tot een gewoon agenda-event (``Post``
kind=event) en wordt ``resolved_post_id`` gezet — nul nieuwe event-infra downstream.

AVG: de maker (``creator_member_id``) is **SET NULL** zodat een samenkomst met open
stemmen waarde houdt als de starter zijn account wist; stemmen/uitnodigingen/datums
zijn **CASCADE** (verdwijnt de prikker of het lid, dan verdwijnt de stem mee).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, GatheringState, GatheringVoteChoice

if TYPE_CHECKING:
    from app.models.member import Member
    from app.models.post import Post


class Gathering(Base):
    __tablename__ = "gathering"

    id: Mapped[int] = mapped_column(primary_key=True)
    # SET NULL: een open prikker houdt waarde voor de groep als de starter zijn
    # account wist (spiegelt Post.added_by_id).
    creator_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("member.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Vrije-tekst plek-hint ("ergens in Utrecht", "online") — geen geocoding (fase 1).
    location_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Waarop de auto-selectie draaide (tag/tool-identifier), puur voor het label
    # ("mensen die met voice-agents bezig zijn"). Nullable = open prikker.
    interest: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[GatheringState] = mapped_column(
        SQLEnum(GatheringState, name="gathering_state", native_enum=False),
        nullable=False,
        default=GatheringState.open,
        server_default=GatheringState.open.value,
        index=True,
    )
    # Gezet bij samenklappen: het agenda-event dat uit de winnende datum ontstond.
    resolved_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("post.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    creator: Mapped[Member | None] = relationship()
    resolved_post: Mapped[Post | None] = relationship()
    dates: Mapped[list[GatheringDate]] = relationship(
        back_populates="gathering",
        cascade="all, delete-orphan",
        order_by="GatheringDate.position, GatheringDate.starts_at",
    )


class GatheringDate(Base):
    __tablename__ = "gathering_date"

    id: Mapped[int] = mapped_column(primary_key=True)
    gathering_id: Mapped[int] = mapped_column(
        ForeignKey("gathering.id", ondelete="CASCADE"), index=True, nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    gathering: Mapped[Gathering] = relationship(back_populates="dates")


class GatheringVote(Base):
    __tablename__ = "gathering_vote"
    __table_args__ = (
        UniqueConstraint(
            "gathering_date_id", "member_id", name="uq_gathering_vote_date_member"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    gathering_date_id: Mapped[int] = mapped_column(
        ForeignKey("gathering_date.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    choice: Mapped[GatheringVoteChoice] = mapped_column(
        SQLEnum(GatheringVoteChoice, name="gathering_vote_choice", native_enum=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    member: Mapped[Member] = relationship()


class GatheringInvite(Base):
    __tablename__ = "gathering_invite"
    __table_args__ = (
        UniqueConstraint(
            "gathering_id", "member_id", name="uq_gathering_invite_gathering_member"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    gathering_id: Mapped[int] = mapped_column(
        ForeignKey("gathering.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    member: Mapped[Member] = relationship()
