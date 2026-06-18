"""RoadmapItem model (E3) — een item op de levende, transparante roadmap.

Admin-curated (CRUD), gegroepeerd per ``phase`` en gesorteerd op ``position``.
``status`` is een ``RoadmapStatus``-enum als VARCHAR (native_enum=False) → DDL
``String(length=9)`` ("overwegen"). ``linked_idea_id`` koppelt een gepromoot idee;
de FK is ``ondelete=SET NULL`` zodat een verwijderd/gewist idee het roadmap-item
laat staan (alleen de link valt weg).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, RoadmapStatus

if TYPE_CHECKING:
    from app.models.idea import Idea


class RoadmapItem(Base):
    __tablename__ = "roadmap_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RoadmapStatus] = mapped_column(
        SQLEnum(RoadmapStatus, name="roadmap_status", native_enum=False),
        default=RoadmapStatus.overwegen,
        nullable=False,
        index=True,
    )
    phase: Mapped[str] = mapped_column(String(80), nullable=False, default="Later")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # SET NULL: een verwijderd/gewist idee laat het roadmap-item staan; alleen de
    # koppeling valt weg.
    linked_idea_id: Mapped[int | None] = mapped_column(
        ForeignKey("idea.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    linked_idea: Mapped[Idea | None] = relationship()
