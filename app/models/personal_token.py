"""PersonalToken model (MCP-server) — een persoonlijk Bearer-token per lid.

Laat een lid z'n AI-tool (Claude Code / Cursor / eigen agent) bij de dewereldvan
MCP-server authenticeren. Spiegelt het magic-link-patroon: **alleen de hash**
(``security.hash_token`` = sha256 + SECRET_KEY) wordt opgeslagen; de ruwe token
(prefix ``dwv_``) wordt één keer getoond en is nooit terug te halen.

Grenzen (precies de invite-grant-grens): een token = "act as dit *approved* lid",
nooit role-escalatie. ``revoked_at`` trekt in zonder te verwijderen (spoor);
``last_used_at`` geeft zichtbaarheid. CASCADE op het lid + opname in
``delete_member_completely`` (AVG).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class PersonalToken(Base):
    __tablename__ = "personal_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)

    member: Mapped[Member] = relationship()
