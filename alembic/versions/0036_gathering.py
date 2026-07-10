"""Samenkomen — datumprikker (PRD-samenkomen, fase 1).

Vier tabellen: ``gathering`` (de prikker), ``gathering_date`` (kandidaat-datums),
``gathering_vote`` (één stem per datum+lid, uniek → race-veilige upsert) en
``gathering_invite`` (wie is uitgenodigd, uniek per prikker+lid). Dialect-neutraal
(VARCHAR + CHECK voor de enums). CASCADE waar een stem/datum/uitnodiging waardeloos
wordt zonder z'n ouder; de maker (``creator_member_id``) en het opgeloste event
(``resolved_post_id``) zijn SET NULL (waarde blijft voor de groep).

Revision ID: 0036_gathering
Revises: 0035_profile_cover_video
Create Date: 2026-07-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036_gathering"
down_revision: str | None = "0035_profile_cover_video"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gathering",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creator_member_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location_hint", sa.String(length=200), nullable=True),
        sa.Column("interest", sa.String(length=120), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "open", "resolved", "cancelled",
                name="gathering_state", native_enum=False,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column("resolved_post_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["creator_member_id"], ["member.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_post_id"], ["post.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gathering_creator_member_id"), "gathering", ["creator_member_id"])
    op.create_index(op.f("ix_gathering_state"), "gathering", ["state"])

    op.create_table(
        "gathering_date",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gathering_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["gathering_id"], ["gathering.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gathering_date_gathering_id"), "gathering_date", ["gathering_id"])

    op.create_table(
        "gathering_vote",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gathering_date_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column(
            "choice",
            sa.Enum(
                "yes", "maybe", "no",
                name="gathering_vote_choice", native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["gathering_date_id"], ["gathering_date.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gathering_date_id", "member_id", name="uq_gathering_vote_date_member"),
    )
    op.create_index(op.f("ix_gathering_vote_gathering_date_id"), "gathering_vote", ["gathering_date_id"])
    op.create_index(op.f("ix_gathering_vote_member_id"), "gathering_vote", ["member_id"])

    op.create_table(
        "gathering_invite",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("gathering_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["gathering_id"], ["gathering.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gathering_id", "member_id", name="uq_gathering_invite_gathering_member"),
    )
    op.create_index(op.f("ix_gathering_invite_gathering_id"), "gathering_invite", ["gathering_id"])
    op.create_index(op.f("ix_gathering_invite_member_id"), "gathering_invite", ["member_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_gathering_invite_member_id"), table_name="gathering_invite")
    op.drop_index(op.f("ix_gathering_invite_gathering_id"), table_name="gathering_invite")
    op.drop_table("gathering_invite")
    op.drop_index(op.f("ix_gathering_vote_member_id"), table_name="gathering_vote")
    op.drop_index(op.f("ix_gathering_vote_gathering_date_id"), table_name="gathering_vote")
    op.drop_table("gathering_vote")
    op.drop_index(op.f("ix_gathering_date_gathering_id"), table_name="gathering_date")
    op.drop_table("gathering_date")
    op.drop_index(op.f("ix_gathering_state"), table_name="gathering")
    op.drop_index(op.f("ix_gathering_creator_member_id"), table_name="gathering")
    op.drop_table("gathering")
