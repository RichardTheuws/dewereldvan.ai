"""AI-native profielbouw (F1-F3) — additive schema.

Voegt toe (breekt geen bestaande tabellen):
- ``profile``: headline, cover_image_url, ai_enriched, ai_source_text
- ``offering``: url, image_url
- nieuwe tabel ``profile_link`` (rollen/affiliaties + builds met beeld)
- nieuwe tabel ``ai_chat_turn`` (server-side conversatie-state voor de bouw-flow)

``ai_enriched`` krijgt ``server_default=sa.false()`` zodat bestaande rijen geldig
blijven onder de NOT NULL-constraint. Enums staan model-side op
``native_enum=False`` → VARCHAR; de kolom is hier dus ``String``.

Revision ID: 0003_ai_profile
Revises: 0002_profile_consent
Create Date: 2026-06-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_ai_profile"
down_revision: str | None = "0002_profile_consent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- profile: AI-build velden ---
    op.add_column("profile", sa.Column("headline", sa.String(length=200), nullable=True))
    op.add_column(
        "profile", sa.Column("cover_image_url", sa.String(length=1000), nullable=True)
    )
    op.add_column(
        "profile",
        sa.Column(
            "ai_enriched",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("profile", sa.Column("ai_source_text", sa.Text(), nullable=True))

    # --- offering: link + beeld ---
    op.add_column("offering", sa.Column("url", sa.String(length=1000), nullable=True))
    op.add_column(
        "offering", sa.Column("image_url", sa.String(length=1000), nullable=True)
    )

    # --- nieuwe tabel: profile_link ---
    op.create_table(
        "profile_link",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        # native_enum=False → VARCHAR; CHECK volgt het model.
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="other"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_profile_link_profile_id", "profile_link", ["profile_id"])

    # --- nieuwe tabel: ai_chat_turn (conversatie-state) ---
    op.create_table(
        "ai_chat_turn",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ai_chat_turn_member_id", "ai_chat_turn", ["member_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_chat_turn_member_id", table_name="ai_chat_turn")
    op.drop_table("ai_chat_turn")
    op.drop_index("ix_profile_link_profile_id", table_name="profile_link")
    op.drop_table("profile_link")
    op.drop_column("offering", "image_url")
    op.drop_column("offering", "url")
    op.drop_column("profile", "ai_source_text")
    op.drop_column("profile", "ai_enriched")
    op.drop_column("profile", "cover_image_url")
    op.drop_column("profile", "headline")
