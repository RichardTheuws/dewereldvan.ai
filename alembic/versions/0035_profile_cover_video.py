"""Video-hero — ``cover_video_url`` op ``profile``.

Additieve nullable kolom: pad naar een geüploade mp4 onder ``UPLOAD_DIR``
(geserveerd via ``/uploads``). Heeft voorrang op ``cover_image_url`` in de
hero-render (video → beeld → nevel).

Revision ID: 0035_profile_cover_video
Revises: 0034_profile_cover_locked
Create Date: 2026-07-01

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035_profile_cover_video"
down_revision: str | None = "0034_profile_cover_locked"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile",
        sa.Column("cover_video_url", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profile", "cover_video_url")
