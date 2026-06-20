"""DiscoveryRun.passes — onthoud welke focus-passes voltooid zijn.

Zodat de UI de vervolgstap kan aanpassen (bv. media al doorzocht → bied 'm niet
opnieuw aan). JSON-lijst in een Text-kolom; nullable (oude rijen = nog niets).

Revision ID: 0021_discovery_run_passes
Revises: 0020_notification_channels
Create Date: 2026-06-20

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_discovery_run_passes"
down_revision: str | None = "0020_notification_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("discovery_run", sa.Column("passes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("discovery_run", "passes")
