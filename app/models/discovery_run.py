"""DiscoveryRun — één lopende/afgeronde footprint-ontdekking per lid.

De ontdekking duurt minuten (echte web-search + weging), te lang om iemand op één
verbinding vast te houden. Daarom ontkoppelen we 'm: een achtergrond-thread draait
de engine en schrijft de bevindingen hierheen; de live-view *tailt* deze rij, en
wie wegklikt verliest niets — bij terugkeer staat het resultaat er nog, en een
seintje (in-app chip + e-mail) haalt het lid terug.

Eén rij per lid (``member_id`` uniek): een nieuwe ontdekking hergebruikt/reset de
rij (de laatste run telt). ``findings_json`` draagt de gesaneerde ``Finding``-dicts
(zelfde vorm als het ``candidate``-SSE-event), zodat de live-tail én de
terugkeer-view exact dezelfde 1b-kaarten renderen. Self-only (AVG): mee-gewist bij
account-verwijdering.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class DiscoveryRun(Base):
    __tablename__ = "discovery_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Eén run per lid (de laatste); CASCADE + opname in delete_member_completely.
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    # "running" | "done" | "empty" | "failed" — vrije string (geen DB-enum, spiegelt
    # de nudge-``kind``-aanpak; status-constanten leven in discovery_job_service).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    # JSON-lijst van gesaneerde finding-dicts (title/url/type/confidence/why).
    findings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Wanneer het lid het afgeronde resultaat zag (stuurt de "klaar"-chip).
    seen_at: Mapped[datetime | None] = mapped_column(nullable=True)

    member: Mapped[Member] = relationship()
