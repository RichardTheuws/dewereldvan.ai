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


def test_tool_seed_ran_on_postgres(pg):
    """0018 seed draaide: de gegronde AI-tool-catalogus staat erin (dialect-proof
    op Postgres, incl. de TimestampMixin-default ``created_at``)."""
    engine, _ = pg
    with engine.begin() as conn:
        tools = conn.execute(text("SELECT count(*) FROM tool")).scalar()
        claude = conn.execute(
            text("SELECT created_at FROM tool WHERE slug = 'claude-code'")
        ).first()
    assert tools >= 25  # ~30 gezaaide tools
    assert claude is not None and claude[0] is not None  # server_default now()


def test_profile_tool_link_writes_on_postgres(pg):
    """Smoke-CRUD op de nieuwe M2M: een profiel ↔ tool-koppeling schrijft + leest
    op Postgres (composite-PK + dubbele CASCADE-FK + unique-constraint)."""
    engine, _ = pg
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO member (email, name, status, role) "
                "VALUES ('pg-tool@example.com', 'PG Tool', 'approved', 'member')"
            )
        )
        mid = conn.execute(
            text("SELECT id FROM member WHERE email = 'pg-tool@example.com'")
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO profile (member_id, slug, display_name, visibility, "
                "completeness, emphasis, ai_enriched) "
                "VALUES (:mid, 'pg-tool', 'PG Tool', 'public', 0, 'balanced', false)"
            ).bindparams(mid=mid)
        )
        pid = conn.execute(
            text("SELECT id FROM profile WHERE slug = 'pg-tool'")
        ).scalar()
        tid = conn.execute(
            text("SELECT id FROM tool WHERE slug = 'claude-code'")
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO profile_tool (profile_id, tool_id) VALUES (:p, :t)"
            ).bindparams(p=pid, t=tid)
        )
        linked = conn.execute(
            text(
                "SELECT count(*) FROM profile_tool WHERE profile_id = :p "
                "AND tool_id = :t"
            ).bindparams(p=pid, t=tid)
        ).scalar()
    assert linked == 1


def test_profile_tool_cascade_on_profile_delete_on_postgres(pg):
    """AVG-vangnet: delete het profiel → de ``profile_tool``-koppelrij verdwijnt
    automatisch (DB-CASCADE vuurt) terwijl de gedeelde ``tool``-master blijft."""
    engine, _ = pg
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO member (email, name, status, role) "
                "VALUES ('pg-casc@example.com', 'PG Cascade', 'approved', 'member')"
            )
        )
        mid = conn.execute(
            text("SELECT id FROM member WHERE email = 'pg-casc@example.com'")
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO profile (member_id, slug, display_name, visibility, "
                "completeness, emphasis, ai_enriched) "
                "VALUES (:mid, 'pg-casc', 'PG Cascade', 'public', 0, 'balanced', "
                "false)"
            ).bindparams(mid=mid)
        )
        pid = conn.execute(
            text("SELECT id FROM profile WHERE slug = 'pg-casc'")
        ).scalar()
        tid = conn.execute(
            text("SELECT id FROM tool WHERE slug = 'claude-code'")
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO profile_tool (profile_id, tool_id) VALUES (:p, :t)"
            ).bindparams(p=pid, t=tid)
        )

    # Delete het profiel → de CASCADE-FK moet de koppelrij meenemen.
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM profile WHERE id = :p").bindparams(p=pid)
        )

    with engine.begin() as conn:
        links = conn.execute(
            text(
                "SELECT count(*) FROM profile_tool WHERE profile_id = :p"
            ).bindparams(p=pid)
        ).scalar()
        tool_still = conn.execute(
            text("SELECT count(*) FROM tool WHERE id = :t").bindparams(t=tid)
        ).scalar()
    assert links == 0  # CASCADE vuurde: koppelrij weg
    assert tool_still == 1  # gedeelde master blijft bestaan


def test_downgrade_base_and_back(pg):
    """De keten is volledig reversibel op Postgres (downgrade base → upgrade head)."""
    engine, cfg = pg
    command.downgrade(cfg, "base")
    assert "post" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "post" in inspect(engine).get_table_names()
