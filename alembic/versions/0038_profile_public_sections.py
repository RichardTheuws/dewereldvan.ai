"""Sectie-niveau zichtbaarheid — profile.public_sections (PRD-zichtbaarheid-secties).

Eén nullable JSON(B)-lijst op ``profile``: bij ``visibility=public`` bepaalt ze welke
blokken (bio/makes/needs/open_to) een BEZOEKER ziet. ``NULL`` = alle blokken publiek
(legacy/backwards-compatible). JSONB op Postgres (de ledengids distinct't hele
Profile-rijen → een gewone json-kolom zou DISTINCT breken; zie 0031). Additief, geen
backfill; verdwijnt mee met het profiel (CASCADE op member) — AVG.

Revision ID: 0038_profile_public_sections
Revises: 0037_profile_area
Create Date: 2026-07-11

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0038_profile_public_sections"
down_revision: str | None = "0037_profile_area"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON_LIST = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("profile", sa.Column("public_sections", _JSON_LIST, nullable=True))


def downgrade() -> None:
    op.drop_column("profile", "public_sections")
