"""AiChatTurn model — server-side conversation state for AI-native profielbouw.

Beslissing (zie bouwcontract §3e): de conversatie-state leeft in de DB, niet in
een signed session-cookie. Tool-blokken en thinking-blokken moeten byte-exact
over meerdere turns teruggestuurd worden naar de Anthropic-API; die passen niet
in een 4KB-cookie en mogen niet client-side manipuleerbaar zijn. Redis is
verworpen (extra leverancier tegen de lage-op-last-eis); Postgres staat er al.

Eén rij per turn. ``content_json`` is ``json.dumps`` van het content-blok (incl.
tool/thinking) zodat het ongewijzigd teruggestuurd kan worden. Het row-count-in-
window-patroon (zie ``magic_link._recent_count``) telt ``role="user"``-rijen per
lid voor de rate-limit-guard.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class AiChatTurn(Base):
    __tablename__ = "ai_chat_turn"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    # json.dumps van het content-blok (incl. tool/thinking) — ongewijzigd terug.
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    member: Mapped[Member] = relationship(back_populates="ai_chat_turns")
