"""MatchSuggestion model (Tier 1) — een gevonden koppeling need ↔ offering.

De kern-visie: andermans ``Need`` koppelen aan jouw ``Offering`` (en omgekeerd).
De match-engine (``match_service``) genereert kandidaten met goedkope SQL en laat
Claude op échte complementariteit oordelen (score + gegronde "waarom"-zin); het
resultaat wordt hier gepersisteerd zodat:

- de push-chip "iemand zoekt wat jij maakt" op ``status == new`` kan triggeren,
- een dismiss sticky blijft (``status == dismissed``),
- de digest/surface ernaar kan verwijzen zonder elke paginaload te herrekenen.

FK's zijn **CASCADE**: verdwijnt de need of offering (of het lid), dan verdwijnt de
suggestie mee — er valt dan immers niets meer te koppelen. ``seeker_member_id`` /
``maker_member_id`` zijn gedenormaliseerd (afgeleid van need.profile / offering.
profile) zodat de chip- en digest-query's niet door twee joins hoeven. Uniek
``(need_id, offering_id)`` houdt herrekenen idempotent.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MatchStatus

if TYPE_CHECKING:
    from app.models.need import Need
    from app.models.offering import Offering


class MatchSuggestion(Base):
    __tablename__ = "match_suggestion"
    __table_args__ = (
        UniqueConstraint("need_id", "offering_id", name="uq_match_need_offering"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    need_id: Mapped[int] = mapped_column(
        ForeignKey("need.id", ondelete="CASCADE"), index=True, nullable=False
    )
    offering_id: Mapped[int] = mapped_column(
        ForeignKey("offering.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Gedenormaliseerd (afgeleid bij creatie) — voor goedkope chip/digest-query's.
    seeker_member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    maker_member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[MatchStatus] = mapped_column(
        SQLEnum(MatchStatus, name="match_status", native_enum=False),
        default=MatchStatus.new,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    need: Mapped[Need] = relationship()
    offering: Mapped[Offering] = relationship()
