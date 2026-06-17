"""Baseline: all Fase-1 tables (member, magic_link, profile, tag, profile_tag,
offering, need, audit_log).

Enums are emitted as VARCHAR + CHECK (native_enum=False) so the schema is
identical on Postgres (prod) and SQLite (tests). No match/post/comment tables
— those arrive later as additive migrations.

Revision ID: 0001_initial_fase1
Revises:
Create Date: 2026-06-17

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_fase1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "suspended",
                "rejected",
                name="member_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("member", "admin", name="member_role", native_enum=False),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("pending_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_member_email", "member", ["email"], unique=True)
    op.create_index("ix_member_status", "member", ["status"], unique=False)

    op.create_table(
        "magic_link_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("requested_ip", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_magic_link_token_member_id", "magic_link_token", ["member_id"], unique=False
    )
    op.create_index(
        "ix_magic_link_token_token_hash", "magic_link_token", ["token_hash"], unique=True
    )

    op.create_table(
        "profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("makes_summary", sa.Text(), nullable=True),
        sa.Column(
            "visibility",
            sa.Enum(
                "members", "public", name="profile_visibility", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("completeness", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id"),
    )
    op.create_index("ix_profile_slug", "profile", ["slug"], unique=True)
    op.create_index("ix_profile_visibility", "profile", ["visibility"], unique=False)

    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_slug", "tag", ["slug"], unique=True)

    op.create_table(
        "profile_tag",
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id", "tag_id"),
    )

    op.create_table(
        "offering",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profile.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offering_profile_id", "offering", ["profile_id"], unique=False)

    op.create_table(
        "need",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profile.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_need_profile_id", "need", ["profile_id"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "member_approved",
                "member_rejected",
                "member_suspended",
                "visibility_changed",
                name="audit_action",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("actor_member_id", sa.Integer(), nullable=True),
        sa.Column("target_member_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_member_id"], ["member.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_member_id"], ["member.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_need_profile_id", table_name="need")
    op.drop_table("need")
    op.drop_index("ix_offering_profile_id", table_name="offering")
    op.drop_table("offering")
    op.drop_table("profile_tag")
    op.drop_index("ix_tag_slug", table_name="tag")
    op.drop_table("tag")
    op.drop_index("ix_profile_visibility", table_name="profile")
    op.drop_index("ix_profile_slug", table_name="profile")
    op.drop_table("profile")
    op.drop_index("ix_magic_link_token_token_hash", table_name="magic_link_token")
    op.drop_index("ix_magic_link_token_member_id", table_name="magic_link_token")
    op.drop_table("magic_link_token")
    op.drop_index("ix_member_status", table_name="member")
    op.drop_index("ix_member_email", table_name="member")
    op.drop_table("member")
