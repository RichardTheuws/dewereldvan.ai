"""AiSpendLog — append-only kasboek van betaalde niet-lid-AI-calls.

Fundament voor de bezoeker-AI-kostengovernance (doc 04 §4.1). Eén rij per call
met echte token-usage + bevroren kost (``cost_eur_micros``). Geen member_id (de
telunit is de signed-cookie ``visitor_id``). Indexen op de tel-kolommen
(visitor_id / ip / prompt_hash / created_at) zodat de gate-queries goedkoop zijn.

Dialect-neutraal (Postgres-proof): ``created_at`` via ``server_default=now()``;
concept/prompt_hash als String (geen DB-enum).

Revision ID: 0022_ai_spend_log
Revises: 0021_discovery_run_passes
Create Date: 2026-06-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022_ai_spend_log"
down_revision: str | None = "0021_discovery_run_passes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_spend_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("visitor_id", sa.String(length=64), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=False),
        sa.Column("concept", sa.String(length=16), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_eur_micros", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        # Gegenereerde uitkomst voor de identieke-prompt-cache (Fase 2); nullable.
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_spend_log_visitor_id", "ai_spend_log", ["visitor_id"], unique=False
    )
    op.create_index("ix_ai_spend_log_ip", "ai_spend_log", ["ip"], unique=False)
    op.create_index(
        "ix_ai_spend_log_prompt_hash", "ai_spend_log", ["prompt_hash"], unique=False
    )
    op.create_index(
        "ix_ai_spend_log_created_at", "ai_spend_log", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_ai_spend_log_created_at", table_name="ai_spend_log")
    op.drop_index("ix_ai_spend_log_prompt_hash", table_name="ai_spend_log")
    op.drop_index("ix_ai_spend_log_ip", table_name="ai_spend_log")
    op.drop_index("ix_ai_spend_log_visitor_id", table_name="ai_spend_log")
    op.drop_table("ai_spend_log")
