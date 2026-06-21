"""Tool-review-note — mens-naast-AI-correctie/aanvulling (doc 03 §4.3/§5.1, Fase C).

Een nieuwe lichtgewicht tabel ``tool_review_note``: een lid kan een review-veld
corrigeren/aanvullen; die rij wordt NAAST het AI-blok getoond ("Aangevuld door
<lid>"), nooit stil over de AI heen. Analoog aan ``idea``/``feedback``.

- ``tool_id``  → tool, CASCADE (een verwijderde tool neemt zijn aanvullingen mee).
- ``member_id``→ member, SET NULL (de aanvulling overleeft AVG-verwijdering van
  het lid; verliest dan enkel de attributie).
- ``field``    → welk review-veld (bv. 'limitations'); nullable = algemeen.
- ``hidden``   → lichtgewicht admin-moderatie (geen zware queue).

Additief, geen backfill. De ``audit_action``-kolom is een VARCHAR-enum → de nieuwe
moderatie-actie ``tool_note_hidden`` vergt GEEN migratie.

Revision ID: 0025_tool_review_note
Revises: 0024_tool_review
Create Date: 2026-06-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025_tool_review_note"
down_revision: str | None = "0024_tool_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_review_note",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tool_id",
            sa.Integer(),
            sa.ForeignKey("tool.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("field", sa.String(length=40), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "hidden", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_tool_review_note_tool_id", "tool_review_note", ["tool_id"]
    )
    op.create_index(
        "ix_tool_review_note_member_id", "tool_review_note", ["member_id"]
    )
    op.create_index(
        "ix_tool_review_note_hidden", "tool_review_note", ["hidden"]
    )
    op.create_index(
        "ix_tool_review_note_created_at", "tool_review_note", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_tool_review_note_created_at", table_name="tool_review_note")
    op.drop_index("ix_tool_review_note_hidden", table_name="tool_review_note")
    op.drop_index("ix_tool_review_note_member_id", table_name="tool_review_note")
    op.drop_index("ix_tool_review_note_tool_id", table_name="tool_review_note")
    op.drop_table("tool_review_note")
