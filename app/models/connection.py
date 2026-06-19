"""Connection model (Tier 1 Fase 2) — een persistente intro tussen twee leden.

Verzilvert een match: "stel me voor aan X" eindigde in Fase 1 in een chat-prompt
(dood spoor). Nu persisteert het een ``Connection`` en notificeert het de
ontvanger (e-mail + chip). De ontvanger accepteert of wijst af; bij ``accepted``
opent de contact-/voortzetting-poort (consent).

- ``from_member_id`` / ``to_member_id``: CASCADE — verdwijnt een van beide leden,
  dan verdwijnt de intro mee (er valt niets meer te verbinden). AVG-wis dekt dit
  expliciet (SQLite handhaaft CASCADE niet).
- ``match_suggestion_id``: **SET NULL** — de intro blijft staan als de
  onderliggende match later wegvalt (herrekend/gewist); alleen de context-link valt weg.
- ``message``: de door de initiatiefnemer bevestigde intro-tekst (consent op de
  inhoud die de ontvanger ziet).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ConnectionStatus

if TYPE_CHECKING:
    from app.models.match_suggestion import MatchSuggestion
    from app.models.member import Member


class Connection(Base):
    __tablename__ = "connection"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    match_suggestion_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_suggestion.id", ondelete="SET NULL"), nullable=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[ConnectionStatus] = mapped_column(
        SQLEnum(ConnectionStatus, name="connection_status", native_enum=False),
        default=ConnectionStatus.pending,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(nullable=True)

    from_member: Mapped[Member] = relationship(foreign_keys=[from_member_id])
    to_member: Mapped[Member] = relationship(foreign_keys=[to_member_id])
    match: Mapped[MatchSuggestion | None] = relationship()
