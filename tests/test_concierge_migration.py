"""Migratie-chain test voor de Concierge-laag (0006_concierge).

Bouwt de volledige schema via Alembic op een wegwerp-SQLite-DB-file en
verifieert dat de additieve objecten bestaan zonder drift t.o.v. ``Base.metadata``:
- ``member.is_founder`` + ``member.origin_story`` kolommen.
- de ``concierge_nudge_dismissal``-tabel + unieke (member_id, nudge_kind).

``alembic/env.py`` resolvet de URL uit ``settings.database_url`` (niet uit
``alembic.ini``), dus we patchen die singleton voor de duur van de run naar een
wegwerp-DB-file (geen ``:memory:`` — die overleeft geen tweede connectie).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import settings
from sqlalchemy import create_engine, inspect


def _cfg(root: Path) -> Config:
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


@pytest.fixture
def migrated(monkeypatch):
    """upgrade head op een wegwerp-DB-file; yield (engine, cfg). Cleanup achteraf."""
    root = Path(__file__).resolve().parents[1]
    db_path = Path(tempfile.mkstemp(suffix=".db", prefix="dwv-mig-")[1])
    url = f"sqlite+pysqlite:///{db_path}"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = _cfg(root)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    try:
        yield engine, cfg
    finally:
        engine.dispose()
        db_path.unlink(missing_ok=True)


def test_migration_chain_builds_concierge_schema(migrated):
    engine, _ = migrated
    insp = inspect(engine)

    member_cols = {c["name"] for c in insp.get_columns("member")}
    assert "is_founder" in member_cols
    assert "origin_story" in member_cols

    assert "concierge_nudge_dismissal" in insp.get_table_names()
    nudge_cols = {c["name"] for c in insp.get_columns("concierge_nudge_dismissal")}
    assert {"id", "member_id", "nudge_kind", "dismissed_at"} <= nudge_cols

    uniques = insp.get_unique_constraints("concierge_nudge_dismissal")
    assert any(
        set(u["column_names"]) == {"member_id", "nudge_kind"} for u in uniques
    )


def test_migration_downgrade_is_reversible(migrated):
    engine, cfg = migrated
    # Downgrade to the revision BEFORE the concierge layer (explicit target — a
    # relative "-1" would break the moment another migration is stacked on head).
    command.downgrade(cfg, "0005_ervaring")
    insp = inspect(engine)
    assert "concierge_nudge_dismissal" not in insp.get_table_names()
    assert "is_founder" not in {c["name"] for c in insp.get_columns("member")}
    # Opnieuw vooruit moet weer schoon lukken.
    command.upgrade(cfg, "head")
    insp2 = inspect(engine)
    assert "concierge_nudge_dismissal" in insp2.get_table_names()
