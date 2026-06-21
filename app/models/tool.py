"""Tool model and the profile_tool association table (M2M).

Spiegelt het tag-systeem (``app/models/tag.py``): een gedeelde, canonieke
catalogus van AI-tools die leden aan hun profiel koppelen. Anders dan een tag
draagt een tool ook een optionele ``url`` (link naar de tool) en een ``logo_url``
(best-effort opgehaald logo, nullable). De associatie is een classic ``Table``
met composite-PK + dubbele ``ondelete="CASCADE"`` FK's (de composite-PK
garandeert de uniciteit al, exact zoals ``profile_tag``).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.profile import Profile


profile_tool = Table(
    "profile_tool",
    Base.metadata,
    Column(
        "profile_id",
        ForeignKey("profile.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tool_id",
        ForeignKey("tool.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Tool(Base, TimestampMixin):
    __tablename__ = "tool"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)  # canoniek
    slug: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, nullable=False
    )  # normalized
    # Link naar de tool (door het lid getypt of uit de catalogus). nullable.
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Best-effort opgehaald logo (favicon/og:image -> WEBP onder UPLOAD_DIR).
    # Relatief serveer-pad (``/uploads/<naam>``). None => letter-tile fallback.
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # AI-tool-review (doc 03) — gestructureerd "dossier" (geen sterren), gegrond
    # op de tool-website via Browser Rendering + één Claude-call. ``sa.JSON`` is
    # dialect-neutraal (JSONB op PG, JSON op SQLite). ``reviewed_at`` stuurt de
    # 90-daagse cadans; ``review_status`` ('ok'|'failed'|'no_source') de UI-staat.
    # Een falende review laat de OUDE ``tool_review`` staan (nooit met leeg over-
    # schrijven). Het lid-correctie-pad is Fase C (nog niet hier).
    tool_review: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    tool_review_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    profiles: Mapped[list[Profile]] = relationship(
        secondary=profile_tool, back_populates="tools"
    )
