"""Offering slug-history — oude slug -> offering, voor 301-redirects (PRD L4).

Bij hernoemen van een project krijgt de offering een nieuwe slug; de oude slug
wordt hier vastgelegd zodat ``/projecten/{oude-slug}`` 301-redirect naar de
huidige URL (behoud van linkwaarde). De service ``offering_slug`` (SERVICES)
schrijft de rijen; FOUNDATION bezit het model + de DDL (alle migratie bij één
owner, geen race).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class OfferingSlugHistory(Base, TimestampMixin):
    __tablename__ = "offering_slug_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    offering_id: Mapped[int] = mapped_column(
        ForeignKey("offering.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Een oude slug verwijst naar precies één huidige offering; uniek zodat een
    # historische URL deterministisch redirect.
    old_slug: Mapped[str] = mapped_column(
        String(200), unique=True, index=True, nullable=False
    )
