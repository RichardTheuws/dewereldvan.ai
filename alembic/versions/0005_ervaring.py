"""Ervaring-laag (E1-E4) — additieve schema bovenop de ledenpagina (0004).

Voegt vier nieuwe tabellen toe (breekt geen bestaande tabel, geen backfill nodig):
- ``feedback``      : altijd-bereikbare "deel je gedachte" overal (E1).
- ``idea``          : ledenideeen in de ideeenbus (E2).
- ``idea_vote``     : upvotes (uniek per lid per idee, hard via constraint) (E2).
- ``roadmap_item``  : levende, admin-curated roadmap (E3).

Enum-kolommen (``idea.status``, ``roadmap_item.status``) staan model-side op
``native_enum=False`` → VARCHAR; de DDL-kolom is hier dus ``sa.String(length=9)``
(de langste waarde: "afgewezen" / "overwegen"), exact het precedent van
``member_status`` / ``emphasis`` (0004) zodat de migratie-built schema drift-vrij
blijft tegen ``Base.metadata`` op zowel Postgres (prod) als SQLite (tests).

Boolean-defaults via ``sa.false()`` (werkt op beide dialects).

Revision ID: 0005_ervaring
Revises: 0004_ledenpagina
Create Date: 2026-06-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_ervaring"
down_revision: str | None = "0004_ledenpagina"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- feedback (E1) ---
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("page_path", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "kind", sa.String(length=40), nullable=False, server_default="algemeen"
        ),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column(
            "hidden", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_feedback_member_id", "feedback", ["member_id"])
    op.create_index("ix_feedback_hidden", "feedback", ["hidden"])

    # --- idea (E2) ---
    op.create_table(
        "idea",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        # native_enum=False → VARCHAR; langste waarde "afgewezen" = 9.
        sa.Column(
            "status", sa.String(length=9), nullable=False, server_default="open"
        ),
        sa.Column(
            "hidden", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_idea_member_id", "idea", ["member_id"])
    op.create_index("ix_idea_status", "idea", ["status"])
    op.create_index("ix_idea_hidden", "idea", ["hidden"])

    # --- idea_vote (E2) ---
    op.create_table(
        "idea_vote",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "idea_id",
            sa.Integer(),
            sa.ForeignKey("idea.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idea_id", "member_id", name="uq_idea_vote"),
    )
    op.create_index("ix_idea_vote_idea_id", "idea_vote", ["idea_id"])
    op.create_index("ix_idea_vote_member_id", "idea_vote", ["member_id"])

    # --- roadmap_item (E3) ---
    op.create_table(
        "roadmap_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # native_enum=False → VARCHAR; langste waarde "overwegen" = 9.
        sa.Column(
            "status",
            sa.String(length=9),
            nullable=False,
            server_default="overwegen",
        ),
        sa.Column(
            "phase", sa.String(length=80), nullable=False, server_default="Later"
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "linked_idea_id",
            sa.Integer(),
            # SET NULL: verwijderd idee laat het roadmap-item staan.
            sa.ForeignKey("idea.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_roadmap_item_status", "roadmap_item", ["status"])
    op.create_index(
        "ix_roadmap_item_linked_idea_id", "roadmap_item", ["linked_idea_id"]
    )


def downgrade() -> None:
    # Drop in omgekeerde FK-volgorde (roadmap_item -> idea_vote -> idea -> feedback).
    op.drop_index("ix_roadmap_item_linked_idea_id", table_name="roadmap_item")
    op.drop_index("ix_roadmap_item_status", table_name="roadmap_item")
    op.drop_table("roadmap_item")

    op.drop_index("ix_idea_vote_member_id", table_name="idea_vote")
    op.drop_index("ix_idea_vote_idea_id", table_name="idea_vote")
    op.drop_table("idea_vote")

    op.drop_index("ix_idea_hidden", table_name="idea")
    op.drop_index("ix_idea_status", table_name="idea")
    op.drop_index("ix_idea_member_id", table_name="idea")
    op.drop_table("idea")

    op.drop_index("ix_feedback_hidden", table_name="feedback")
    op.drop_index("ix_feedback_member_id", table_name="feedback")
    op.drop_table("feedback")
