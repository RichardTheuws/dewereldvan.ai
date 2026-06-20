"""DiscoveryRun — achtergrond-footprint-ontdekking per lid (Fase 1b-async).

Eén rij per lid (``member_id`` uniek): de laatste ontdekking. Draagt de status +
de gepersisteerde findings zodat de live-tail én de terugkeer-view dezelfde
1b-kaarten renderen, en wie wegklikt niets verliest. CASCADE op het lid (AVG).

Dialect-neutraal (Postgres-proof): ``created_at`` via ``server_default=now()``;
overige tijdstempels nullable zonder default; status als String (geen DB-enum).

Revision ID: 0019_discovery_run
Revises: 0018_seed_tools
Create Date: 2026-06-20

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_discovery_run"
down_revision: str | None = "0018_seed_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("findings_json", sa.Text(), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("seen_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_discovery_run_member_id", "discovery_run", ["member_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_discovery_run_member_id", table_name="discovery_run")
    op.drop_table("discovery_run")
