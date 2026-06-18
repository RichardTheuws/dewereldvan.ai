"""Idea model (E2) — ledenideeen in de ideeenbus.

Een idee hoort bij een lid (``member_id`` NOT NULL, CASCADE → AVG-verwijdering).
``status`` is een ``IdeaStatus``-enum opgeslagen als VARCHAR (native_enum=False) —
DDL-kolom ``String(length=9)`` ("afgewezen"). ``hidden`` is admin-moderatie. De
stemmen leven in ``IdeaVote`` (uniek per lid per idee, hard via DB-constraint).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdeaStatus

if TYPE_CHECKING:
    from app.models.idea_vote import IdeaVote
    from app.models.member import Member


class Idea(Base):
    __tablename__ = "idea"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IdeaStatus] = mapped_column(
        SQLEnum(IdeaStatus, name="idea_status", native_enum=False),
        default=IdeaStatus.open,
        nullable=False,
        index=True,
    )
    hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    member: Mapped[Member] = relationship()
    votes: Mapped[list[IdeaVote]] = relationship(
        back_populates="idea", cascade="all, delete-orphan"
    )
