"""Member profile model (1:1 with Member)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ProfileEmphasis, TimestampMixin, Visibility

if TYPE_CHECKING:
    from app.models.member import Member
    from app.models.need import Need
    from app.models.offering import Offering
    from app.models.profile_link import ProfileLink
    from app.models.tag import Tag
    from app.models.tool import Tool


class Profile(Base, TimestampMixin):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    slug: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, nullable=False
    )  # for public URL
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)  # "over jezelf"
    makes_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # korte "wat ik maak"
    visibility: Mapped[Visibility] = mapped_column(
        SQLEnum(Visibility, name="profile_visibility", native_enum=False),
        default=Visibility.members,
        nullable=False,
        index=True,
    )
    completeness: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # 0-100, recomputed on save
    # AVG: proof of explicit consent the moment the profile went public.
    # Set when visibility flips to ``public`` with consent; never auto-set.
    consented_public_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    # Layout-prominentie (PRD L1): person | projects | balanced (default).
    emphasis: Mapped[ProfileEmphasis] = mapped_column(
        SQLEnum(ProfileEmphasis, name="profile_emphasis", native_enum=False),
        default=ProfileEmphasis.balanced,
        nullable=False,
    )
    # Pad/URL naar de geüploade profielfoto (relatief, bv. "/uploads/<naam>.webp").
    # Het beeld zelf staat op het /app/data-volume; alleen het pad in de DB.
    # None => fallback (AI-cover of initialen).
    photo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # AI-native profielbouw (F1-F3). All additive; default to "no AI build yet".
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ai_enriched: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Raw member input kept for audit / regenerate; cascades away on member delete.
    ai_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    member: Mapped[Member] = relationship(back_populates="profile")
    offerings: Mapped[list[Offering]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    needs: Mapped[list[Need]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary="profile_tag", back_populates="profiles"
    )
    tools: Mapped[list[Tool]] = relationship(
        secondary="profile_tool", back_populates="profiles"
    )
    profile_links: Mapped[list[ProfileLink]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="ProfileLink.position",
    )
