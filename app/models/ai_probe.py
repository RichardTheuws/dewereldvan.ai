"""AiProbe (PRD hub §4.4) — de maandelijkse AI-steekproef per openbaar profiel.

Per (profiel, maand, vraag) één rij: stelde Claude met web-search een realistische
vraag, werd het lid genoemd, en stond dewereldvan.ai tussen de bronnen. Eerlijk
benoemd als steekproef met Claude, geen "ChatGPT-ranking". CASCADE op profiel.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

_JSON_LIST = JSON().with_variant(postgresql.JSONB(), "postgresql")


class AiProbe(Base):
    __tablename__ = "ai_probe"
    __table_args__ = (
        UniqueConstraint("profile_id", "month", "question", name="uq_ai_probe_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True, nullable=False
    )
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # "2026-11"
    question: Mapped[str] = mapped_column(String(300), nullable=False)
    mentioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hub_cited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answer_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list | None] = mapped_column(_JSON_LIST, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
