"""Agenda-categorie op een event.

Additieve kolom op ``post``:
- ``category`` (VARCHAR + CHECK via native_enum=False, nullable): de soort agenda-
  event (meetup/conferentie/coding/workshop/talk/hackathon/overig). Voedt de
  categorie-badge + de filterchips op /agenda. Nullable zodat bestaande rijen
  ongemoeid blijven; nieuwe events krijgen default ``meetup`` (in de service).

Dialect-neutraal (VARCHAR + CHECK werkt op Postgres én SQLite).

Revision ID: 0032_event_category
Revises: 0031_json_to_jsonb
Create Date: 2026-06-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0032_event_category"
down_revision: str | None = "0031_json_to_jsonb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORY = sa.Enum(
    "meetup",
    "conferentie",
    "coding",
    "workshop",
    "talk",
    "hackathon",
    "overig",
    name="event_category",
    native_enum=False,
)


def upgrade() -> None:
    op.add_column("post", sa.Column("category", _CATEGORY, nullable=True))


def downgrade() -> None:
    op.drop_column("post", "category")
