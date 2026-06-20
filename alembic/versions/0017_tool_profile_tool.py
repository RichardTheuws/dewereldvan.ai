"""AI-toolsets op profielen — ``tool``-catalogus + ``profile_tool``-assoc (M2M).

Spiegelt het tag-systeem (0001): een gedeelde, canonieke ``tool``-tabel + een
``profile_tool``-koppeltabel met composite-PK en dubbele ``ondelete=CASCADE``-FK.
Extra t.o.v. tag: ``url``/``logo_url`` (nullable String(1000)) en ``created_at``
(TimestampMixin, ``server_default=now()``). De composite-PK garandeert de
uniciteit al (geen aparte unique-constraint, exact zoals ``profile_tag``).

Dialect-neutraal (Postgres-proof): geen boolean-default-valkuil; alle extra
kolommen nullable zonder default. ``created_at``/``updated_at`` gebruiken
``sa.func.now()`` zoals de bestaande TimestampMixin-tabellen (0001).

Revision ID: 0017_tool_profile_tool
Revises: 0016_offering_enrich
Create Date: 2026-06-20

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017_tool_profile_tool"
down_revision: str | None = "0016_offering_enrich"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("logo_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_slug", "tool", ["slug"], unique=True)

    op.create_table(
        "profile_tool",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("tool_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_id"], ["tool.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id", "tool_id"),
    )


def downgrade() -> None:
    op.drop_table("profile_tool")
    op.drop_index("ix_tool_slug", table_name="tool")
    op.drop_table("tool")
