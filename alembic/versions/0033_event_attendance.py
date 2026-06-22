"""RSVP / aanwezigheid op een agenda-event — de sociale laag.

Nieuwe tabel ``event_attendance``: één rij per (event, lid) met een rol
(attending/organizing/speaking). Unieke constraint ``(post_id, member_id)`` →
één rol per lid per event (her-zetten = update). Beide FK's CASCADE (AVG: event
of lid weg → aanmelding weg). Dialect-neutraal (VARCHAR + CHECK voor de rol).

Revision ID: 0033_event_attendance
Revises: 0032_event_category
Create Date: 2026-06-22

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0033_event_attendance"
down_revision: str | None = "0032_event_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_attendance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "attending",
                "organizing",
                "speaking",
                name="event_attendance_role",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["post.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "member_id", name="uq_event_attendance_post_member"),
    )
    op.create_index(
        op.f("ix_event_attendance_post_id"), "event_attendance", ["post_id"]
    )
    op.create_index(
        op.f("ix_event_attendance_member_id"), "event_attendance", ["member_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_event_attendance_member_id"), table_name="event_attendance")
    op.drop_index(op.f("ix_event_attendance_post_id"), table_name="event_attendance")
    op.drop_table("event_attendance")
