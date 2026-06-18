"""Group-invite model — één deelbare, herroepbare WhatsApp-uitnodigingslink.

PRD-verificatie-links §0 (vereenvoudigde richting): één ACTIEVE link tegelijk —
de nieuwste niet-verlopen, niet-revoked rij. Wie 'm opent kan DIRECT een profiel
bouwen (pre-approved, geen admin-queue). 24u TTL; een admin regenereert (en doodt
zo een gelekte link). De grant is uitsluitend "word approved lid + bouw profiel";
nooit role/admin-escalatie.

Het raw token is high-entropy (``secrets.token_urlsafe(32)``) en wordt — anders
dan magic-links — wél opgeslagen: het zit per ontwerp in een gedeelde URL die
rondgaat in de groep, dus er is geen geheimhouding-tegenover-de-DB te winnen door
hashing; herroepbaarheid + korte TTL zijn de leak-controle.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

if TYPE_CHECKING:
    pass


class GroupInvite(Base):
    __tablename__ = "group_invite"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    # Wie de link genereerde (een admin). SET NULL zodat een verwijderd
    # admin-account de audit-spoor-rij niet meesleept.
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("member.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
