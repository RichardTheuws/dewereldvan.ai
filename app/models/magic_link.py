"""Single-use, hashed magic-link token model.

The raw token is NEVER persisted — only its sha256 hex digest. A token is
valid iff ``used_at IS NULL AND expires_at > now()`` and the hash matches.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.member import Member


class MagicLinkToken(Base):
    __tablename__ = "magic_link_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # sha256 hex; raw token NEVER stored.
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)  # single-use marker
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    # Rate-limit support, AVG-minimal.
    requested_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    member: Mapped[Member] = relationship(back_populates="magic_links")
