"""Member-geheugen — gedistilleerd, sessie-overstijgend concierge-geheugen.

Additieve kolommen op ``member`` (Concierge-intelligentie Fase 2):
- ``member_memory`` (Text, nullable): compacte, door de AI gedistilleerde "wat ik
  over dit lid weet" uit eerdere concierge-gesprekken.
- ``memory_synced_turn_id`` (Integer, nullable): hoogwatermerk — t/m welke
  ``concierge_turn.id`` het geheugen is bijgewerkt (maakt de distill-job idempotent
  en goedkoop: alleen leden met nieuwere turns worden opnieuw gedistilleerd).

Geen enum/boolean/server_default → geen dialect-valkuilen (dialect-neutraal,
Postgres-proof; vgl. de 0010-les). Wordt automatisch meegewist bij
``delete_member_completely`` (de member-row verdwijnt).

Revision ID: 0015_member_memory
Revises: 0014_personal_token
Create Date: 2026-06-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_member_memory"
down_revision: str | None = "0014_personal_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("member", sa.Column("member_memory", sa.Text(), nullable=True))
    op.add_column(
        "member",
        sa.Column("memory_synced_turn_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("member", "memory_synced_turn_id")
    op.drop_column("member", "member_memory")
