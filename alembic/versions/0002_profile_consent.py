"""Additive columns: profile consent proof + member registration IP.

- ``profile.consented_public_at``: AVG (PRD §4) requires explicit consent when
  a profile is published. Records the moment consent was given; NULL means
  never public with consent.
- ``member.registration_ip``: source IP of an open registration, used to
  rate-limit anonymous registration per IP (abuse / e-mail-bomb protection).

Revision ID: 0002_profile_consent
Revises: 0001_initial_fase1
Create Date: 2026-06-17

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_profile_consent"
down_revision: str | None = "0001_initial_fase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile",
        sa.Column("consented_public_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "member",
        sa.Column("registration_ip", sa.String(length=45), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("member", "registration_ip")
    op.drop_column("profile", "consented_public_at")
