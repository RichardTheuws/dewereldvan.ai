"""Spam-triage bij registratie — korte reden op het lid (pivot Fase B).

Additieve kolom op ``member``:
- ``triage_note`` (Text, nullable): de korte reden van de spam-triage bij
  registratie (waarom auto-welkom of in de review-queue). Puur voor de admin-
  queue; geen oordeel over de persoon. None = niet getrieerd (AI uit → handmatig).

Nullable, geen default → dialect-neutraal (Postgres-proof). Bestaande leden
houden ``NULL`` (zijn al goedgekeurd; triage geldt alleen voor nieuwe aanmeldingen).

Revision ID: 0026_member_triage_note
Revises: 0025_tool_review_note
Create Date: 2026-06-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026_member_triage_note"
down_revision: str | None = "0025_tool_review_note"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("member", sa.Column("triage_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("member", "triage_note")
