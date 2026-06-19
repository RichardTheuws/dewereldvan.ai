"""Project-verrijking — screenshot-hero + AI-samenvatting op een offering.

Additieve kolommen op ``offering``:
- ``screenshot_url`` (String, nullable): relatief serveer-pad naar de screenshot
  van de project-link (Cloudflare Browser Rendering → WEBP onder UPLOAD_DIR). De
  hero valt terug op het bestaande ``image_url`` als er (nog) geen screenshot is.
- ``summary`` (Text, nullable): korte, gegronde AI-samenvatting van de pagina-
  inhoud (los van de door het lid getypte ``description``).

Beide nullable, geen default → dialect-neutraal (Postgres-proof). Worden via de
``enrich_projects``-job gevuld voor offerings met een URL maar zonder verrijking;
bij een URL-wijziging nullt de inline-edit ze zodat ze opnieuw genereren.

Revision ID: 0016_offering_enrich
Revises: 0015_member_memory
Create Date: 2026-06-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_offering_enrich"
down_revision: str | None = "0015_member_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "offering", sa.Column("screenshot_url", sa.String(length=1000), nullable=True)
    )
    op.add_column("offering", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("offering", "summary")
    op.drop_column("offering", "screenshot_url")
