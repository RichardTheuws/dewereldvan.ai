"""ProfileLink model — rich links on a profile (affiliations + builds).

Introduced for AI-native profielbouw (F1-F3). A profile_link captures a
role/affiliation ("verantwoordelijk voor X") or something the member builds,
with an optional URL, description, and image (og:image / logo). Distinct from
``Offering`` (which is the member's own "wat ik maak") and ``Need``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, ProfileLinkKind, TimestampMixin

if TYPE_CHECKING:
    from app.models.profile import Profile


class ProfileLink(Base, TimestampMixin):
    __tablename__ = "profile_link"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    kind: Mapped[ProfileLinkKind] = mapped_column(
        # native_enum=False → VARCHAR + CHECK; identical schema on SQLite/Postgres.
        SQLEnum(ProfileLinkKind, name="profile_link_kind", native_enum=False),
        default=ProfileLinkKind.other,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    profile: Mapped[Profile] = relationship(back_populates="profile_links")
