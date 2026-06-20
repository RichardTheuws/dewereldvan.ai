"""Notificatie-kanalen — member_channel + notification_pref.

Lid-gekozen push-notificatiekanaal (Telegram eerst, uitbreidbaar). ``member_channel``
draagt het gekoppelde adres (chat_id) per kanaal; ``notification_pref`` het gekozen
voorkeurskanaal (default in_app = pull-chip). Beide CASCADE op het lid (AVG).

Dialect-neutraal (Postgres-proof): ``created_at`` via ``server_default=now()``;
overige tijdstempels nullable; kanaal/adres als String (geen DB-enum).

Revision ID: 0020_notification_channels
Revises: 0019_discovery_run
Create Date: 2026-06-20

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_notification_channels"
down_revision: str | None = "0019_discovery_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member_channel",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=True),
        sa.Column("link_token", sa.String(length=64), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id", "channel", name="uq_member_channel"),
    )
    op.create_index(
        "ix_member_channel_member_id", "member_channel", ["member_id"], unique=False
    )
    op.create_index(
        "ix_member_channel_link_token", "member_channel", ["link_token"], unique=True
    )

    op.create_table(
        "notification_pref",
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("member_id"),
    )


def downgrade() -> None:
    op.drop_table("notification_pref")
    op.drop_index("ix_member_channel_link_token", table_name="member_channel")
    op.drop_index("ix_member_channel_member_id", table_name="member_channel")
    op.drop_table("member_channel")
