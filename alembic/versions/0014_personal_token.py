"""PersonalToken — persoonlijk Bearer-token per lid (MCP-server).

Additieve tabel. ``member_id`` CASCADE; ``token_hash`` uniek (alleen de hash, nooit
de ruwe token). Geen enum/boolean → geen dialect-valkuilen.

Revision ID: 0014_personal_token
Revises: 0013_connection
Create Date: 2026-06-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014_personal_token"
down_revision: str | None = "0013_connection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_token",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_personal_token_hash"),
    )
    op.create_index("ix_personal_token_member_id", "personal_token", ["member_id"])
    op.create_index("ix_personal_token_token_hash", "personal_token", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_personal_token_token_hash", table_name="personal_token")
    op.drop_index("ix_personal_token_member_id", table_name="personal_token")
    op.drop_table("personal_token")
