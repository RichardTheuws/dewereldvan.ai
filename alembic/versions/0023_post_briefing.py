"""Post — "De Briefing": AI-gecureerde nieuws-kandidaten met mens-in-de-lus.

Voegt vijf nullable kolommen toe aan ``post`` (AUGMENT, doc 02 §4 — geen tweede
tabel):
- ``review_state`` (live | pending_review | rejected, default live) — lid-flow
  blijft ``live``; AI-kandidaten starten ``pending_review`` (nooit silent-publish).
- ``source_kind`` (member | ai_curated | member_media, default member) — herkomst.
- ``ai_relevance`` (int, nullable) — de curatie-score (alleen AI-kandidaten).
- ``ai_take`` (Text, nullable) — de "waarom dit ertoe doet"-duiding.
- ``briefing_week`` (Date, nullable) — ISO-week-ankerdag voor de briefing-strip.

Additief, geen backfill: bestaande rijen krijgen de server_default (live/member).
Enums als VARCHAR + CHECK (native_enum=False, test-pariteit). De review-transities
zelf zijn additieve ``audit_action``-waarden (VARCHAR-enum) → geen migratie nodig.

Revision ID: 0023_post_briefing
Revises: 0022_ai_spend_log
Create Date: 2026-06-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_post_briefing"
down_revision: str | None = "0022_ai_spend_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "post",
        sa.Column(
            "review_state",
            sa.Enum(
                "live",
                "pending_review",
                "rejected",
                name="post_review_state",
                native_enum=False,
            ),
            nullable=False,
            server_default="live",
        ),
    )
    op.add_column(
        "post",
        sa.Column(
            "source_kind",
            sa.Enum(
                "member",
                "ai_curated",
                "member_media",
                name="post_source_kind",
                native_enum=False,
            ),
            nullable=False,
            server_default="member",
        ),
    )
    op.add_column("post", sa.Column("ai_relevance", sa.Integer(), nullable=True))
    op.add_column("post", sa.Column("ai_take", sa.Text(), nullable=True))
    op.add_column("post", sa.Column("briefing_week", sa.Date(), nullable=True))
    op.create_index("ix_post_review_state", "post", ["review_state"])
    op.create_index("ix_post_briefing_week", "post", ["briefing_week"])


def downgrade() -> None:
    op.drop_index("ix_post_briefing_week", table_name="post")
    op.drop_index("ix_post_review_state", table_name="post")
    op.drop_column("post", "briefing_week")
    op.drop_column("post", "ai_take")
    op.drop_column("post", "ai_relevance")
    op.drop_column("post", "source_kind")
    op.drop_column("post", "review_state")
