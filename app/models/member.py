"""Member account model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, MemberRole, MemberStatus, TimestampMixin

if TYPE_CHECKING:
    from app.models.ai_chat import AiChatTurn
    from app.models.magic_link import MagicLinkToken
    from app.models.profile import Profile


class Member(Base, TimestampMixin):
    __tablename__ = "member"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Store lowercased; uniqueness enforced case-folded at the service layer.
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[MemberStatus] = mapped_column(
        SQLEnum(MemberStatus, name="member_status", native_enum=False),
        default=MemberStatus.pending,
        nullable=False,
        index=True,
    )
    role: Mapped[MemberRole] = mapped_column(
        SQLEnum(MemberRole, name="member_role", native_enum=False),
        default=MemberRole.member,
        nullable=False,
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    pending_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Source IP of the registration request — used to rate-limit anonymous
    # open registration per IP (abuse / e-mail-bomb protection).
    registration_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    profile: Mapped[Profile | None] = relationship(
        back_populates="member", uselist=False, cascade="all, delete-orphan"
    )
    magic_links: Mapped[list[MagicLinkToken]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
    ai_chat_turns: Mapped[list[AiChatTurn]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
