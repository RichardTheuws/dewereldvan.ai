"""Postgres-pariteit — draait de migratie-keten + smoke-CRUD tegen een ECHTE
Postgres (niet SQLite), zodat dialect-bugs vóór productie rood worden i.p.v. via
een handmatige prod-browsertest.

**Default GESKIPT**: de snelle SQLite-suite (``conftest.py``, ``create_all``) blijft
de standaard. Activeer dit pad door een Postgres-URL te zetten:

    TEST_DATABASE_URL=postgresql+psycopg://app:app@localhost:5544/dewereldvan_test

of draai gewoon ``scripts/test-postgres.sh`` (spint een wegwerp-Postgres in Docker).
CI zet dezelfde env via een ``postgres:16``-service (zie ``.github/workflows/ci.yml``).

ACHTERGROND — waarom dit bestaat: twee migraties glipten door de SQLite-tests en
faalden pas op Postgres (alleen gevangen door een handmatige live-test in prod):
- ``0008`` — ``audit_log.action`` VARCHAR te kort → ``StringDataRightTruncation``.
- ``0010`` — ``hidden`` boolean ``server_default=text('0')`` → ``DatatypeMismatch``.
SQLite negeert VARCHAR-lengtes én accepteert losse boolean-defaults, dus die klasse
is op SQLite onzichtbaar. ``test_upgrade_head_succeeds_on_postgres`` zou ze beide
rood hebben gemaakt op ``alembic upgrade head``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import settings
from sqlalchemy import create_engine, inspect, text

PG_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not PG_URL.startswith("postgresql"),
    reason="TEST_DATABASE_URL (Postgres) niet gezet — Postgres-pariteit-test geskipt",
)


def _cfg(root: Path) -> Config:
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


@pytest.fixture
def pg(monkeypatch):
    """Schone lei op de echte Postgres, dan ``alembic upgrade head``.

    Drop + hercreëer ``public`` zodat de run hermetisch is, ook bij een herhaalde
    lokale draai. Patcht ``settings.database_url`` (env.py leest die singleton).
    """
    root = Path(__file__).resolve().parents[1]
    engine = create_engine(PG_URL, future=True)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    monkeypatch.setattr(settings, "database_url", PG_URL)
    cfg = _cfg(root)
    command.upgrade(cfg, "head")
    try:
        yield engine, cfg
    finally:
        engine.dispose()


def test_upgrade_head_succeeds_on_postgres(pg):
    """De kern-guard: de volledige keten bouwt op Postgres. Zou 0008 + 0010 rood
    hebben gemaakt (de upgrade zelf crasht bij een dialect-bug)."""
    engine, _ = pg
    tables = set(inspect(engine).get_table_names())
    assert {"member", "profile", "post", "idea", "roadmap_item"} <= tables


def test_post_boolean_default_writes_on_postgres(pg):
    """0010-regressievanger: insert zónder ``hidden`` → de DB-default moet werken
    op Postgres (waar ``server_default=text('0')`` op een boolean zou crashen)."""
    engine, _ = pg
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO post (kind, title) VALUES ('event', 'Smoke')")
        )
        row = conn.execute(
            text("SELECT hidden FROM post WHERE title = 'Smoke'")
        ).first()
    assert row is not None
    assert row[0] is False  # boolean-default klopt op Postgres


def test_seed_migration_ran_on_postgres(pg):
    """0011 seed draaide: de gegronde agenda-events staan erin (bewijst dat de
    data-migratie ook op Postgres werkt, niet alleen op SQLite)."""
    engine, _ = pg
    with engine.begin() as conn:
        events = conn.execute(
            text("SELECT count(*) FROM post WHERE kind = 'event'")
        ).scalar()
        roadmap = conn.execute(text("SELECT count(*) FROM roadmap_item")).scalar()
    assert events >= 2
    assert roadmap >= 1


def test_downgrade_base_and_back(pg):
    """De keten is volledig reversibel op Postgres (downgrade base → upgrade head)."""
    engine, cfg = pg
    command.downgrade(cfg, "base")
    assert "post" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "post" in inspect(engine).get_table_names()
