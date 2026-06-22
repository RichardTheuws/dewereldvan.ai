"""Galerij-werk-item — externe beeld-URLs op een offering (pivot Fase C, inc. 4).

Additieve kolom op ``offering`` (voor ``kind='gallery'``):
- ``gallery_urls`` (JSON, nullable): de lijst gehotlinkte beeld-URLs van een
  portfolio-/galerij-pagina, geëxtraheerd uit de geplakte link
  (``project_enrich_service.extract_gallery_images``). Nul-opslag: de browser van
  de bezoeker haalt de beelden, niet onze server.

Nullable, geen default → dialect-neutraal (JSON werkt op zowel Postgres als SQLite).

Revision ID: 0029_offering_gallery
Revises: 0028_offering_event
Create Date: 2026-06-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029_offering_gallery"
down_revision: str | None = "0028_offering_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("offering", sa.Column("gallery_urls", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("offering", "gallery_urls")
