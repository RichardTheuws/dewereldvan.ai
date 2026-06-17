"""Tag model and the profile_tag association table (M2M)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.profile import Profile


profile_tag = Table(
    "profile_tag",
    Base.metadata,
    Column(
        "profile_id",
        ForeignKey("profile.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        ForeignKey("tag.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(60), unique=True, index=True, nullable=False
    )  # normalized
    profiles: Mapped[list[Profile]] = relationship(
        secondary=profile_tag, back_populates="tags"
    )
