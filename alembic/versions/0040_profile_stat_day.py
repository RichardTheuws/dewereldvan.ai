"""Anonieme dagtellers per profiel — ``profile_stat_day`` (PRD hub §4.4).

Additief, geen backfill. Alleen getallen (geen IP/UA). CASCADE op profiel.

Revision ID: 0040_profile_stat_day
Revises: 0039_inquiry
Create Date: 2026-10-16

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0040_profile_stat_day"
down_revision: str | None = "0039_inquiry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_stat_day",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("profile_id", "day", "kind", name="uq_profile_stat_day"),
    )
    op.create_index("ix_profile_stat_day_profile_id", "profile_stat_day", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_profile_stat_day_profile_id", table_name="profile_stat_day")
    op.drop_table("profile_stat_day")
