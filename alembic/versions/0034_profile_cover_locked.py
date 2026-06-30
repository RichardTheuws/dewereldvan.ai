"""Hero-studio — ``cover_locked`` op ``profile``.

Additieve boolean-kolom: het lid heeft zijn cover vastgezet ("Hou deze") zodat de
AUTOMATIEK (auto-cover na materialisatie / her-verrijking) hem niet overschrijft.
Een expliciete lid-generatie in de hero-studio negeert de lock bewust.

``server_default`` op false zodat bestaande rijen een geldige waarde krijgen;
dialect-neutraal (``sa.false()`` rendert per dialect correct).

Revision ID: 0034_profile_cover_locked
Revises: 0033_event_attendance
Create Date: 2026-06-30

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034_profile_cover_locked"
down_revision: str | None = "0033_event_attendance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile",
        sa.Column(
            "cover_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("profile", "cover_locked")
