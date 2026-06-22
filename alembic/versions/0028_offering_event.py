"""Workshop/sessie-werk-item — datum + locatie op een offering (pivot Fase C, inc. 2).

Additieve kolommen op ``offering`` (voor ``kind='workshop'``):
- ``event_at`` (DateTime, nullable): wanneer de workshop/sessie is/was.
- ``location`` (String, nullable): 'Online', een plaats of een venue.

Beide nullable, geen default → dialect-neutraal. Gevuld door de agent-extractie
(``project_enrich_service.extract_event``) uit een geplakte event-/workshop-link.

Revision ID: 0028_offering_event
Revises: 0027_offering_kind_embed
Create Date: 2026-06-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028_offering_event"
down_revision: str | None = "0027_offering_kind_embed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("offering", sa.Column("event_at", sa.DateTime(), nullable=True))
    op.add_column("offering", sa.Column("location", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("offering", "location")
    op.drop_column("offering", "event_at")
