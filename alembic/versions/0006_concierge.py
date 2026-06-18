"""Concierge-laag — additieve schema bovenop de ervaring-laag (0005).

Voegt toe (breekt geen bestaande tabel, geen backfill nodig):
- ``member.is_founder``   : bool (default false) — herkende mede-oprichter.
- ``member.origin_story`` : Text (nullable) — het ontstaansverhaal, los van bio.
- ``concierge_nudge_dismissal`` : frequency-cap voor proactieve suggesties
  (één rij per member+nudge_kind; uniek via constraint).

Boolean-default via ``sa.false()`` (werkt op Postgres én SQLite). De nieuwe
kolommen krijgen een server_default voor de bestaande rijen; het ORM-model zet
geen server_default (Python-side default volstaat daar) — exact het 0004/0005-
precedent zodat de migratie-built schema drift-vrij blijft tegen ``Base.metadata``.

Revision ID: 0006_concierge
Revises: 0005_ervaring
Create Date: 2026-06-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_concierge"
down_revision: str | None = "0005_ervaring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- member: founder-herkenning + ontstaansverhaal ---
    op.add_column(
        "member",
        sa.Column(
            "is_founder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "member",
        sa.Column("origin_story", sa.Text(), nullable=True),
    )

    # --- concierge_nudge_dismissal: frequency-cap ---
    op.create_table(
        "concierge_nudge_dismissal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nudge_kind", sa.String(length=120), nullable=False),
        sa.Column(
            "dismissed_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "member_id", "nudge_kind", name="uq_concierge_nudge"
        ),
    )
    op.create_index(
        "ix_concierge_nudge_dismissal_member_id",
        "concierge_nudge_dismissal",
        ["member_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_concierge_nudge_dismissal_member_id",
        table_name="concierge_nudge_dismissal",
    )
    op.drop_table("concierge_nudge_dismissal")
    op.drop_column("member", "origin_story")
    op.drop_column("member", "is_founder")
