"""Tool-review — AI-dossier per gebruikte tool (doc 03 §5.1).

Voegt drie nullable kolommen toe aan ``tool`` (AUGMENT, geen tweede tabel):
- ``tool_review`` (JSON, nullable) — de gestructureerde review (zie §5-schema).
  ``sa.JSON`` is dialect-neutraal: JSONB op Postgres, JSON op SQLite.
- ``tool_reviewed_at`` (DateTime, nullable) — wanneer voor het laatst gereviewd
  (stuurt de 90-daagse re-review-cadans).
- ``tool_review_status`` (String, nullable) — 'ok' | 'failed' | 'no_source'
  (fail-zichtbaarheid; een falende fetch laat de OUDE review staan).

Additief, geen backfill: bestaande rijen blijven NULL → "nog niet gereviewd".
Het lid-correctie-model (``tool_review_note``) is Fase C — niet hier.

Revision ID: 0024_tool_review
Revises: 0023_post_briefing
Create Date: 2026-06-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_tool_review"
down_revision: str | None = "0023_post_briefing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tool", sa.Column("tool_review", sa.JSON(), nullable=True))
    op.add_column(
        "tool", sa.Column("tool_reviewed_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "tool", sa.Column("tool_review_status", sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("tool", "tool_review_status")
    op.drop_column("tool", "tool_reviewed_at")
    op.drop_column("tool", "tool_review")
