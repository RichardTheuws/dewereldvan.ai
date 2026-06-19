"""Connection — persistente intro tussen twee leden (Tier 1 Fase 2).

Additieve tabel. ``from_member_id``/``to_member_id`` CASCADE; ``match_suggestion_id``
SET NULL (de intro overleeft een herrekende/gewiste match). Enum als VARCHAR + CHECK
(native_enum=False, test-pariteit). Boolean-loos; geen ``sa.text('0')``-valkuil.

Revision ID: 0013_connection
Revises: 0012_match_suggestion
Create Date: 2026-06-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_connection"
down_revision: str | None = "0012_match_suggestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "from_member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "match_suggestion_id",
            sa.Integer(),
            sa.ForeignKey("match_suggestion.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "accepted", "declined",
                name="connection_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_connection_from_member_id", "connection", ["from_member_id"])
    op.create_index("ix_connection_to_member_id", "connection", ["to_member_id"])
    op.create_index("ix_connection_status", "connection", ["status"])


def downgrade() -> None:
    op.drop_index("ix_connection_status", table_name="connection")
    op.drop_index("ix_connection_to_member_id", table_name="connection")
    op.drop_index("ix_connection_from_member_id", table_name="connection")
    op.drop_table("connection")
