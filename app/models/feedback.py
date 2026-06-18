"""Feedback model (E1) — altijd-bereikbare "deel je gedachte" overal.

Feedback mag anoniem (uitgelogd) gegeven worden, want de affordance staat ook op
publieke pagina's; daarom is ``member_id`` nullable. De FK is ``ondelete=CASCADE``
zodat een AVG-verwijdering van een lid diens feedback meeneemt. ``page_path`` legt
de paginacontext vast (waar de gedachte vandaan kwam); ``ai_summary`` wordt
best-effort door Claude gevuld (niet-blokkerend) voor het admin-overzicht.
``ip`` wordt alleen voor anonieme inzending vastgelegd, als anker voor de
per-IP rate-limit (ingelogde inzending leunt op ``member_id``).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: anonieme/uitgelogde feedback mag (de affordance staat ook op
    # publieke pagina's). CASCADE → AVG-verwijdering van een lid neemt de
    # feedback mee.
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # Inzender-IP — uitsluitend voor de anonieme rate-limit (member_id IS NULL):
    # ingelogde inzending wordt per lid begrensd, anonieme per IP in een
    # uur-venster (zelfde rij-tel-patroon als ``Member.registration_ip``).
    # Best-effort gevuld (kan NULL zijn zonder client-host).
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    page_path: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="algemeen")
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    member: Mapped[Member | None] = relationship()
