"""Maandelijkse AI-steekproef — tabel ``ai_probe`` (PRD hub §4.4).

Additief, geen backfill. CASCADE op profiel (AVG). ``sources`` als JSONB op Postgres.

Revision ID: 0041_ai_probe
Revises: 0040_profile_stat_day
Create Date: 2026-10-16

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0041_ai_probe"
down_revision: str | None = "0040_profile_stat_day"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON_LIST = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ai_probe",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("question", sa.String(length=300), nullable=False),
        sa.Column("mentioned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hub_cited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("answer_excerpt", sa.Text(), nullable=True),
        sa.Column("sources", _JSON_LIST, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("profile_id", "month", "question", name="uq_ai_probe_question"),
    )
    op.create_index("ix_ai_probe_profile_id", "ai_probe", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_probe_profile_id", table_name="ai_probe")
    op.drop_table("ai_probe")
