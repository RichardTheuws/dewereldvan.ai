"""Post — één holistische community-bijdrage (agenda + nieuws + later meer).

Voegt ``post`` toe: gedeelde velden (title/description/url) + ``kind`` + type-
specifieke nullable velden (event: frequency/next_at/cadence_note/location;
nieuws: source/role/published_at). ``added_by_id`` is SET NULL (de bijdrage blijft
staan als de toevoeger zijn account wist) en nullable (admin/seed). Additieve
tabel, geen backfill. Enums als VARCHAR + CHECK (native_enum=False, test-pariteit).

Revision ID: 0010_post
Revises: 0009_concierge_turn
Create Date: 2026-06-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_post"
down_revision: str | None = "0009_concierge_turn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "post",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "added_by_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "kind",
            sa.Enum("event", "nieuws", name="post_kind", native_enum=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column(
            "hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # event-specifiek
        sa.Column(
            "frequency",
            sa.Enum(
                "eenmalig",
                "wekelijks",
                "tweewekelijks",
                "maandelijks",
                "doorlopend",
                name="event_frequency",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("next_at", sa.DateTime(), nullable=True),
        sa.Column("cadence_note", sa.String(length=120), nullable=True),
        sa.Column("location", sa.String(length=160), nullable=True),
        # nieuws-specifiek
        sa.Column("source", sa.String(length=160), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "geschreven",
                "geinterviewd",
                "vermeld",
                "gedeeld",
                name="news_role",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_post_added_by_id", "post", ["added_by_id"])
    op.create_index("ix_post_kind", "post", ["kind"])
    op.create_index("ix_post_hidden", "post", ["hidden"])


def downgrade() -> None:
    op.drop_index("ix_post_hidden", table_name="post")
    op.drop_index("ix_post_kind", table_name="post")
    op.drop_index("ix_post_added_by_id", table_name="post")
    op.drop_table("post")
