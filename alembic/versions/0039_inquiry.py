"""Aanvragen van bezoekers — tabel ``inquiry`` (PRD hub §4.1).

Additief, geen backfill. CASCADE op member/profile (AVG: verdwijnt mee bij wissen).
Status als ``String(8)`` (native_enum=False, langste waarde 'answered').

Revision ID: 0039_inquiry
Revises: 0038_profile_public_sections
Create Date: 2026-10-16

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0039_inquiry"
down_revision: str | None = "0038_profile_public_sections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inquiry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sender_name", sa.String(length=120), nullable=False),
        sa.Column("sender_email", sa.String(length=320), nullable=False),
        sa.Column("sender_org", sa.String(length=160), nullable=True),
        sa.Column("topic", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("dedupe_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("dedupe_hash", name="uq_inquiry_dedupe_hash"),
    )
    op.create_index("ix_inquiry_member_id", "inquiry", ["member_id"])
    op.create_index("ix_inquiry_profile_id", "inquiry", ["profile_id"])
    op.create_index("ix_inquiry_status", "inquiry", ["status"])
    op.create_index("ix_inquiry_ip_hash", "inquiry", ["ip_hash"])
    op.create_index("ix_inquiry_created_at", "inquiry", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_inquiry_created_at", table_name="inquiry")
    op.drop_index("ix_inquiry_ip_hash", table_name="inquiry")
    op.drop_index("ix_inquiry_status", table_name="inquiry")
    op.drop_index("ix_inquiry_profile_id", table_name="inquiry")
    op.drop_index("ix_inquiry_member_id", table_name="inquiry")
    op.drop_table("inquiry")
