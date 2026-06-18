"""Publieke ledenpagina & profielverrijking (L1-L4) — additieve schema.

Voegt toe (breekt geen bestaande tabellen):
- ``profile``: emphasis (layout-prominentie), photo_url (profielfoto-pad)
- ``offering``: slug (stabiele projectdetail-URL, uniek) + backfill bestaande rijen
- nieuwe tabel ``offering_slug_history`` (oude slug -> offering, voor 301-redirects)

``emphasis`` krijgt ``server_default="balanced"`` zodat bestaande profielen geldig
blijven onder de NOT NULL-constraint. Enums staan model-side op
``native_enum=False`` → VARCHAR; de kolom is hier dus ``String`` (precedent:
``member_status`` / ``audit_action``).

``offering.slug`` is in DDL ``nullable=True`` zodat de additieve kolomtoevoeging
bestaande rijen niet breekt; de backfill hieronder zet meteen een unieke slug op
elke bestaande rij. De service ``offering_slug.ensure_slug`` garandeert daarna dat
nieuwe/bewerkte offerings altijd een slug krijgen.

Revision ID: 0004_ledenpagina
Revises: 0003_ai_profile
Create Date: 2026-06-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_ledenpagina"
down_revision: str | None = "0003_ai_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- profile: emphasis + photo_url ---
    op.add_column(
        "profile",
        sa.Column(
            "emphasis",
            # Match the model exactly: SQLEnum(native_enum=False) derives the
            # VARCHAR length from the longest value ("balanced" = 8), so the
            # migration-built schema stays drift-free against Base.metadata.
            sa.String(length=8),
            nullable=False,
            server_default="balanced",
        ),
    )
    op.add_column(
        "profile", sa.Column("photo_url", sa.String(length=1000), nullable=True)
    )

    # --- offering: slug (nullable in DDL, daarna backfill) ---
    op.add_column("offering", sa.Column("slug", sa.String(length=200), nullable=True))
    op.create_index("ix_offering_slug", "offering", ["slug"], unique=True)

    # Backfill bestaande offering-slugs: slugify(title) + numerieke suffix bij
    # botsing. Importeer de helper hier (binnen de functie) zodat het importeren
    # van de migratie-module zelf geen app-afhankelijkheid forceert.
    from app.security import slugify

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, title FROM offering ORDER BY id")
    ).fetchall()
    used: set[str] = set()
    for oid, title in rows:
        root = slugify(title or f"project-{oid}")
        cand, n = root, 2
        while cand in used:
            cand = f"{root}-{n}"
            n += 1
        used.add(cand)
        bind.execute(
            sa.text("UPDATE offering SET slug=:s WHERE id=:i"),
            {"s": cand, "i": oid},
        )

    # --- nieuwe tabel: offering_slug_history (oude slug -> offering) ---
    op.create_table(
        "offering_slug_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "offering_id",
            sa.Integer(),
            sa.ForeignKey("offering.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_slug", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_offering_slug_history_offering_id",
        "offering_slug_history",
        ["offering_id"],
    )
    op.create_index(
        "ix_offering_slug_history_old_slug",
        "offering_slug_history",
        ["old_slug"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_offering_slug_history_old_slug", table_name="offering_slug_history"
    )
    op.drop_index(
        "ix_offering_slug_history_offering_id", table_name="offering_slug_history"
    )
    op.drop_table("offering_slug_history")
    op.drop_index("ix_offering_slug", table_name="offering")
    op.drop_column("offering", "slug")
    op.drop_column("profile", "photo_url")
    op.drop_column("profile", "emphasis")
