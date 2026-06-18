"""Groep-invite-link — additieve tabel bovenop de concierge-laag (0006).

Voegt de ``group_invite``-tabel toe: één deelbare WhatsApp-uitnodigingslink
(PRD-verificatie-links §0). Breekt geen bestaande tabel, geen backfill nodig.

``revoked`` krijgt een ``server_default`` (``sa.false()`` — werkt op Postgres én
SQLite) voor eventuele bestaande rijen; het ORM-model zet géén server_default
(Python-side default volstaat) — exact het 0006-precedent zodat de migratie-built
schema drift-vrij blijft tegen ``Base.metadata``.

De audit-actie (``invite_generated`` / ``invite_registration``) is een additieve
VARCHAR-enum-waarde → geen DDL nodig.

Revision ID: 0007_group_invite
Revises: 0006_concierge
Create Date: 2026-06-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_group_invite"
down_revision: str | None = "0006_concierge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "group_invite",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "revoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_group_invite_token", "group_invite", ["token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_group_invite_token", table_name="group_invite")
    op.drop_table("group_invite")
