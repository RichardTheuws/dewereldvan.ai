"""MemberChannel — een gekoppeld push-notificatiekanaal-adres per lid.

Uitbreidbaar model (niet één Telegram-veld): elk extern kanaal (telegram, later
whatsapp/push/…) krijgt één rij per lid. Het koppelen verloopt in twee stappen:
1. **link_token** gezet (eenmalig, deep-link), ``address``/``verified_at`` leeg;
2. na bevestiging door het kanaal (bv. Telegram-webhook): ``address`` = het echte
   adres (chat_id), ``verified_at`` = nu, ``link_token`` leeg.

Eén rij per (member, channel). CASCADE op het lid + opname in
``delete_member_completely`` (AVG). Het in-app-kanaal staat NIET hier (dat is de
state-derived pull-chip, altijd beschikbaar).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class MemberChannel(Base):
    __tablename__ = "member_channel"
    __table_args__ = (
        UniqueConstraint("member_id", "channel", name="uq_member_channel"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # bv. "telegram"
    address: Mapped[str | None] = mapped_column(String(128), nullable=True)  # chat_id
    link_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    member: Mapped[Member] = relationship()

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None and bool(self.address)
