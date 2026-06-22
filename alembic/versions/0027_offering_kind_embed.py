"""Multidisciplinaire showcase — werk-item-soort + oEmbed (pivot Fase C, increment 1).

Additieve kolommen op ``offering``:
- ``kind`` (String, NOT NULL, default ``project``): het soort werk-item
  (project/video/audio/workshop/gallery/writing/link). ``server_default='project'``
  zodat bestaande rijen geldig blijven (= het huidige screenshot-hero-gedrag).
- ``embed_html`` (Text, nullable): de gesanitiseerde oEmbed-iframe voor video/audio
  (alleen van een provider-allowlist). Leeg → link-fallback.

Dialect-neutraal (Postgres-proof): ``kind`` als VARCHAR met server_default; de
enum-waarden worden door de app (SQLEnum native_enum=False) afgedwongen.

Revision ID: 0027_offering_kind_embed
Revises: 0026_member_triage_note
Create Date: 2026-06-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027_offering_kind_embed"
down_revision: str | None = "0026_member_triage_note"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "offering",
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default="project",
        ),
    )
    op.add_column("offering", sa.Column("embed_html", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("offering", "embed_html")
    op.drop_column("offering", "kind")
