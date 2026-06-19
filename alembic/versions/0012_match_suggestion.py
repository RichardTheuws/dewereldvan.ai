"""MatchSuggestion — gevonden koppeling need ↔ offering (Tier 1 matchmaking).

Additieve tabel. FK's CASCADE (need/offering/member): verdwijnt een van de drie,
dan verdwijnt de suggestie mee. Uniek (need_id, offering_id) houdt herrekenen
idempotent. Enum als VARCHAR + CHECK (native_enum=False, test-pariteit).

Revision ID: 0012_match_suggestion
Revises: 0011_seed_agenda_roadmap
Create Date: 2026-06-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_match_suggestion"
down_revision: str | None = "0011_seed_agenda_roadmap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_suggestion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "need_id",
            sa.Integer(),
            sa.ForeignKey("need.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "offering_id",
            sa.Integer(),
            sa.ForeignKey("offering.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "seeker_member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "maker_member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum(
                "new", "seen", "dismissed", "acted",
                name="match_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("need_id", "offering_id", name="uq_match_need_offering"),
    )
    op.create_index("ix_match_suggestion_need_id", "match_suggestion", ["need_id"])
    op.create_index(
        "ix_match_suggestion_offering_id", "match_suggestion", ["offering_id"]
    )
    op.create_index(
        "ix_match_suggestion_seeker_member_id", "match_suggestion", ["seeker_member_id"]
    )
    op.create_index(
        "ix_match_suggestion_maker_member_id", "match_suggestion", ["maker_member_id"]
    )
    op.create_index("ix_match_suggestion_status", "match_suggestion", ["status"])


def downgrade() -> None:
    op.drop_index("ix_match_suggestion_status", table_name="match_suggestion")
    op.drop_index("ix_match_suggestion_maker_member_id", table_name="match_suggestion")
    op.drop_index("ix_match_suggestion_seeker_member_id", table_name="match_suggestion")
    op.drop_index("ix_match_suggestion_offering_id", table_name="match_suggestion")
    op.drop_index("ix_match_suggestion_need_id", table_name="match_suggestion")
    op.drop_table("match_suggestion")
