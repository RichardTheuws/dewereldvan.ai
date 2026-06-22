"""Waar ik voor opensta — engagement-beschikbaarheid op een profiel.

Additieve kolom op ``profile``:
- ``open_to`` (JSON, nullable): lijst canonieke openness-slugs (klantwerk/trainingen/
  spreken/interviews/samenwerkingen) die het lid zelf kiest. Signaleert beschikbaarheid,
  los van offerings/needs. Gevuld via de profiel-editor; voedt de publieke beacons +
  de /leden-discovery-filter.

Nullable, geen default → dialect-neutraal (JSON werkt op Postgres én SQLite).

Revision ID: 0030_profile_open_to
Revises: 0029_offering_gallery
Create Date: 2026-06-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030_profile_open_to"
down_revision: str | None = "0029_offering_gallery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profile", sa.Column("open_to", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("profile", "open_to")
