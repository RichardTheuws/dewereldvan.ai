"""Offering model — "wat ik maak" (what a member makes/offers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.profile import Profile


class Offering(Base, TimestampMixin):
    __tablename__ = "offering"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)  # "wat ik maak"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AI-native profielbouw: link + beeld bij een offering (wordt 'project').
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # ordering

    profile: Mapped[Profile] = relationship(back_populates="offerings")
