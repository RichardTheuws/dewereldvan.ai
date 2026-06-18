"""Verbreed audit_log.action naar VARCHAR(64).

De ``audit_action``-kolom (``native_enum=False``) werd in 0001 gesized op de toen-
langste waarde (``visibility_changed`` = 18). Latere additieve waarden waren korter,
tot ``invite_registration`` (19) — die overschreed VARCHAR(18) en brak stil op
Postgres (``StringDataRightTruncation``); SQLite negeert de lengte en miste het.

Fix: verbreed de kolom naar 64 (ruim, ontkoppeld van de enum-waarde-lengte). Het
ORM-model zet nu expliciet ``length=64`` zodat een nieuwe Postgres-DB direct klopt.
Dialect-bewust: alleen op Postgres een echte ALTER; SQLite negeert VARCHAR-lengte,
dus daar een no-op (een type-ALTER zou er bovendien een tabel-rebuild vergen).

Revision ID: 0008_widen_audit_action
Revises: 0007_group_invite
Create Date: 2026-06-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_widen_audit_action"
down_revision: str | None = "0007_group_invite"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "audit_log",
            "action",
            type_=sa.String(length=64),
            existing_type=sa.String(length=18),
            existing_nullable=False,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "audit_log",
            "action",
            type_=sa.String(length=18),
            existing_type=sa.String(length=64),
            existing_nullable=False,
        )
