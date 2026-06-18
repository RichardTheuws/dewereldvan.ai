"""IdeaVote model (E2) — een upvote van een lid op een idee.

Stem-uniekheid wordt HARD afgedwongen via ``UniqueConstraint(idea_id, member_id)``:
één lid kan exact één keer op een idee stemmen. Een dubbele stem raakt een
IntegrityError die de service netjes als "al gestemd" afhandelt (geen 500, geen
dubbele telling). Beide FK's zijn CASCADE (verwijderd idee/lid → stem weg).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.idea import Idea
    from app.models.member import Member


class IdeaVote(Base):
    __tablename__ = "idea_vote"
    __table_args__ = (
        UniqueConstraint("idea_id", "member_id", name="uq_idea_vote"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(
        ForeignKey("idea.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    idea: Mapped[Idea] = relationship(back_populates="votes")
    member: Mapped[Member] = relationship()
