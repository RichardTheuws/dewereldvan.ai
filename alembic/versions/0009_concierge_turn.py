"""Concierge-conversatie-state (Agent-Shell Fase 1) — additieve tabel.

Voegt ``concierge_turn`` toe: één rij per beurt (platte tekst, geen JSON-blokken)
zodat de agent-shell over meerdere acties heen context houdt. Breekt geen bestaande
tabel, geen backfill. CREATE TABLE is dialect-neutraal (Postgres + SQLite), dus geen
dialect-guard nodig.

Revision ID: 0009_concierge_turn
Revises: 0008_widen_audit_action
Create Date: 2026-06-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_concierge_turn"
down_revision: str | None = "0008_widen_audit_action"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "concierge_turn",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_concierge_turn_member_id",
        "concierge_turn",
        ["member_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_concierge_turn_member_id", table_name="concierge_turn")
    op.drop_table("concierge_turn")
