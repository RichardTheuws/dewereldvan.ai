"""json → jsonb voor de list-kolommen (Postgres) — DISTINCT-fix.

Een gewone Postgres ``json``-kolom heeft geen equality-operator, dus ``SELECT
DISTINCT`` over een rij die zo'n kolom bevat faalt. De ledengids distinct't hele
Profile-rijen → ``profile.open_to`` (en voor consistentie ``offering.gallery_urls``)
moeten ``jsonb`` zijn. Alleen op Postgres; op SQLite is json/jsonb hetzelfde (no-op).

Revision ID: 0031_json_to_jsonb
Revises: 0030_profile_open_to
Create Date: 2026-06-22

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0031_json_to_jsonb"
down_revision: str | None = "0030_profile_open_to"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite e.d.: json == jsonb, niets te doen.
    op.alter_column(
        "profile", "open_to",
        type_=postgresql.JSONB(),
        postgresql_using="open_to::jsonb",
    )
    op.alter_column(
        "offering", "gallery_urls",
        type_=postgresql.JSONB(),
        postgresql_using="gallery_urls::jsonb",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.alter_column(
        "offering", "gallery_urls",
        type_=postgresql.JSON(),
        postgresql_using="gallery_urls::json",
    )
    op.alter_column(
        "profile", "open_to",
        type_=postgresql.JSON(),
        postgresql_using="open_to::json",
    )
