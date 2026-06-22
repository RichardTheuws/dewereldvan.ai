"""Offering model — "wat ik maak" (what a member makes/offers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OfferingKind, TimestampMixin
from app.models.types import JSON_LIST

if TYPE_CHECKING:
    from app.models.profile import Profile


class Offering(Base, TimestampMixin):
    __tablename__ = "offering"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)  # "wat ik maak"
    # Stabiele projectdetail-URL (/projecten/{slug}). nullable=True zodat de
    # additieve migratie bestaande rijen niet breekt vóór de backfill; de
    # service (offering_slug.ensure_slug) garandeert dat nieuwe/bewerkte
    # offerings altijd een slug krijgen.
    slug: Mapped[str | None] = mapped_column(
        String(200), unique=True, index=True, nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AI-native profielbouw: link + beeld bij een offering (wordt 'project').
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Project-verrijking (auto, uit de link via Cloudflare Browser Rendering):
    # een screenshot-hero + een gegronde AI-samenvatting van de pagina-inhoud. De
    # hero valt terug op image_url als screenshot_url leeg is; summary staat los
    # van de door het lid getypte description.
    screenshot_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Multidisciplinaire showcase (pivot Fase C): het soort werk-item. ``project``
    # (default) = web-pagina → screenshot-hero. ``video``/``audio`` renderen een
    # ingesloten oEmbed-speler i.p.v. een screenshot (auto-gedetecteerd uit de link).
    kind: Mapped[OfferingKind] = mapped_column(
        SQLEnum(OfferingKind, name="offering_kind", native_enum=False),
        default=OfferingKind.project,
        nullable=False,
    )
    # De gesanitiseerde oEmbed-iframe (alleen voor video/audio). Alleen van een
    # provider-allowlist (YouTube/Vimeo/SoundCloud/Spotify); leeg → link-fallback.
    embed_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Workshop/sessie (kind='workshop'): wanneer + waar. Door de agent geëxtraheerd
    # uit een geplakte event-link (extract_event); beide optioneel.
    event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Galerij (kind='gallery'): een lijst externe beeld-URLs, geëxtraheerd uit de
    # geplakte portfolio-/galerij-link (project_enrich_service.extract_gallery_images).
    # Gehotlinkt (nul-opslag, consistent met de oEmbed-/unfurl-aanpak); de browser van
    # de bezoeker haalt de beelden, niet onze server → geen SSRF, geen storage-op-last.
    gallery_urls: Mapped[list[str] | None] = mapped_column(JSON_LIST, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # ordering

    profile: Mapped[Profile] = relationship(back_populates="offerings")
