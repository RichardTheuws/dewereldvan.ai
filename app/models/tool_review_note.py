"""ToolReviewNote-model (doc 03 §4.3/§5.1) — mens-naast-AI-correctie/aanvulling.

Een lid (expert in het netwerk) kan een review-veld corrigeren/aanvullen. De
correctie wordt NOOIT stil over de AI-review heen geschreven: het is een aparte
rij die NAAST het AI-blok wordt getoond ("Aangevuld door <lid>"). Zo blijft de
herkomst zichtbaar (AI vs mens) en houdt het netwerk de review scherp.

Spiegelt ``Idea``/``Feedback``:
- ``member_id`` is ``ondelete="SET NULL"`` (anders dan Idea's CASCADE): een
  aanvulling is netwerk-kennis die de review beter maakt — bij AVG-verwijdering
  van het lid laten we de tekst staan maar maken 'm anoniem (geen attributie meer).
- ``field`` (nullable): welk review-veld de aanvulling betreft (bv. 'limitations');
  NULL = een algemene aanvulling (geen specifiek veld).
- ``hidden`` is lichtgewicht admin-moderatie (geen zware queue), exact zoals
  ``Idea.hidden``/``Feedback.hidden``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member
    from app.models.tool import Tool


class ToolReviewNote(Base):
    __tablename__ = "tool_review_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(
        ForeignKey("tool.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # SET NULL: de aanvulling overleeft een AVG-verwijdering van het lid (de
    # netwerk-kennis blijft), maar verliest dan de attributie (anoniem getoond).
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("member.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Welk review-veld de aanvulling betreft (bv. 'limitations'); NULL = algemeen.
    field: Mapped[str | None] = mapped_column(String(40), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False, index=True
    )

    member: Mapped[Member | None] = relationship()
    tool: Mapped[Tool] = relationship()
