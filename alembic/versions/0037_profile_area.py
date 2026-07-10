"""Dichtbij — grof + opt-in locatie op het profiel (PRD-samenkomen, fase 2).

Vier nullable kolommen op ``profile``: ``area_code`` (2-cijferig postcode-gebied,
bv. "35"), ``area_label`` (weergavenaam), ``area_lat``/``area_lng`` (afgeleid
middelpunt uit de in-repo PC2-tabel). Nooit een exact adres. Default leeg (opt-in);
verdwijnt mee met het profiel (CASCADE op member) — AVG. Additief, geen backfill.

Revision ID: 0037_profile_area
Revises: 0036_gathering
Create Date: 2026-07-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0037_profile_area"
down_revision: str | None = "0036_gathering"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profile", sa.Column("area_code", sa.String(length=2), nullable=True))
    op.add_column("profile", sa.Column("area_label", sa.String(length=80), nullable=True))
    op.add_column("profile", sa.Column("area_lat", sa.Float(), nullable=True))
    op.add_column("profile", sa.Column("area_lng", sa.Float(), nullable=True))
    op.create_index(op.f("ix_profile_area_code"), "profile", ["area_code"])


def downgrade() -> None:
    op.drop_index(op.f("ix_profile_area_code"), table_name="profile")
    op.drop_column("profile", "area_lng")
    op.drop_column("profile", "area_lat")
    op.drop_column("profile", "area_label")
    op.drop_column("profile", "area_code")
