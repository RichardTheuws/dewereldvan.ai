"""ProfileStatDay (PRD hub §4.4) — anonieme dagtellers per profiel.

Eén rij per (profiel, dag, soort). Geen IP, geen user-agent, geen bezoeker-id:
alleen een getal. Soorten: ``view`` (mens bekeek het profiel), ``ai_fetch`` (een
AI-assistent haalde het op, herkend aan de user-agent), ``mcp_hit`` (het profiel
stond in een anoniem MCP-zoekresultaat). CASCADE op profiel (AVG).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProfileStatDay(Base):
    __tablename__ = "profile_stat_day"
    __table_args__ = (UniqueConstraint("profile_id", "day", "kind", name="uq_profile_stat_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True, nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
