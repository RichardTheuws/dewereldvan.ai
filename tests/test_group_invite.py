"""Tests voor de groep-invite-link (PRD-verificatie-links §0).

Dekt: service-validatie (geldig/verlopen/revoked), register-direct → approved +
ingelogd + redirect /welkom, bestaande-e-mail → inlog zonder duplicaat,
IP-rate-limit, admin generate revoket de oude, niet-admin geweigerd, CSRF op de
POST, en de migratie-keten (0007).

Routevorm: een dedicated wegwerp-engine per test (de routes ``commit`` echte rijen
door de app, dus géén deel van de rollback-geïsoleerde ``db``-fixture) — exact het
``tests/_route_helpers.py``-precedent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests._route_helpers import csrf_token, make_route_engine

NOW = datetime(2026, 6, 18, 12, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Service-laag (rollback-geïsoleerde db-fixture)                              #
# --------------------------------------------------------------------------- #
def test_validate_accepts_active_token(db, make_member):
    from app.models import MemberRole
    from app.services import group_invite as svc

    admin = make_member(email="a@x.nl", role=MemberRole.admin)
    invite = svc.generate(db, admin, now=NOW)
    assert svc.validate(db, invite.token, now=NOW) is not None


def test_validate_rejects_expired_token(db, make_member):
    from app.models import MemberRole
    from app.services import group_invite as svc

    admin = make_member(email="a@x.nl", role=MemberRole.admin)
    invite = svc.generate(db, admin, now=NOW)
    later = NOW + timedelta(hours=25)  # > 24u TTL
    assert svc.validate(db, invite.token, now=later) is None
    assert svc.active_invite(db, now=later) is None


def test_validate_rejects_revoked_token(db, make_member):
    from app.models import MemberRole
    from app.services import group_invite as svc

    admin = make_member(email="a@x.nl", role=MemberRole.admin)
    first = svc.generate(db, admin, now=NOW)
    # Een tweede generate revoket de eerste.
    second = svc.generate(db, admin, now=NOW)
    assert svc.validate(db, first.token, now=NOW) is None
    assert svc.validate(db, second.token, now=NOW) is not None


def test_validate_rejects_empty_and_unknown(db):
    from app.services import group_invite as svc

    assert svc.validate(db, "", now=NOW) is None
    assert svc.validate(db, "does-not-exist", now=NOW) is None


def test_generate_revokes_previous_active(db, make_member):
    from app.models import GroupInvite, MemberRole
    from app.services import group_invite as svc

    admin = make_member(email="a@x.nl", role=MemberRole.admin)
    first = svc.generate(db, admin, now=NOW)
    svc.generate(db, admin, now=NOW)
    db.refresh(first)
    assert first.revoked is True
    # Precies één actieve (niet-revoked) rij.
    active = db.query(GroupInvite).filter(GroupInvite.revoked.is_(False)).all()
    assert len(active) == 1


def test_generate_writes_audit(db, make_member):
    from app.models import AuditAction, AuditLog, MemberRole
    from app.services import group_invite as svc

    admin = make_member(email="a@x.nl", role=MemberRole.admin)
    svc.generate(db, admin, now=NOW)
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action == AuditAction.invite_generated)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor_member_id == admin.id


# --------------------------------------------------------------------------- #
# Route-laag (wegwerp-engine)                                                  #
# --------------------------------------------------------------------------- #
@pytest.fixture
def route_engine():
    eng = make_route_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(
        bind=route_engine, autoflush=False, autocommit=False, future=True
    )


@pytest.fixture
def seed(SessionTest):
    """Eén admin + één actieve invite in de wegwerp-engine."""
    from app.models import Member, MemberRole, MemberStatus
    from app.services import group_invite as svc

    s = SessionTest()
    admin = Member(
        email="admin@example.com",
        name="Beheerder",
        status=MemberStatus.approved,
        role=MemberRole.admin,
    )
    s.add(admin)
    s.commit()
    invite = svc.generate(s, admin)
    s.commit()
    out = {"admin": admin.id, "token": invite.token}
    s.close()
    return out


@pytest.fixture
def make_client(route_engine, SessionTest):
    """Factory: een TestClient met current_member = gekozen lid (of None)."""
    from app.db import get_db
    from app.deps import current_member, email_sender
    from app.main import app
    from app.models import Member

    from tests.conftest import FakeEmailSender

    fake_sender = FakeEmailSender()

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    def _factory(member_id: int | None):
        def _override_current_member(db: Session = Depends(get_db)):
            if member_id is None:
                return None
            return db.get(Member, member_id)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        app.dependency_overrides[email_sender] = lambda: fake_sender
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def _members(SessionTest):
    from app.models import Member

    s = SessionTest()
    try:
        return s.query(Member).all()
    finally:
        s.close()


# --- Landing ---------------------------------------------------------------- #
def test_landing_valid_token_renders_form(make_client, seed):
    client = make_client(None)
    resp = client.get(f"/uitnodiging/{seed['token']}")
    assert resp.status_code == 200
    assert "uitgenodigd" in resp.text.lower()
    assert f'action="/uitnodiging/{seed["token"]}"' in resp.text


def test_landing_invalid_token_shows_expired(make_client, seed):
    client = make_client(None)
    resp = client.get("/uitnodiging/nonsense-token")
    assert resp.status_code == 410
    assert "verlopen" in resp.text.lower()


# --- Register direct -------------------------------------------------------- #
def test_register_direct_creates_approved_and_logs_in(make_client, seed, SessionTest):
    from app.models import MemberStatus

    client = make_client(None)
    token = csrf_token(client, f"/uitnodiging/{seed['token']}")
    resp = client.post(
        f"/uitnodiging/{seed['token']}",
        data={"name": "Nieuw Lid", "email": "nieuw@example.com", "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/welkom"

    s = SessionTest()
    try:
        from app.models import Member

        m = s.query(Member).filter(Member.email == "nieuw@example.com").one()
        assert m.status is MemberStatus.approved
        assert m.approved_at is not None
        assert m.role.value == "member"  # geen escalatie
    finally:
        s.close()


def test_register_existing_pending_promoted_no_duplicate(make_client, seed, SessionTest):
    from app.models import Member, MemberStatus

    s = SessionTest()
    s.add(Member(email="wacht@example.com", name="Wachtend", status=MemberStatus.pending))
    s.commit()
    s.close()

    client = make_client(None)
    token = csrf_token(client, f"/uitnodiging/{seed['token']}")
    resp = client.post(
        f"/uitnodiging/{seed['token']}",
        data={"name": "Wachtend", "email": "wacht@example.com", "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    s = SessionTest()
    try:
        rows = s.query(Member).filter(Member.email == "wacht@example.com").all()
        assert len(rows) == 1  # geen duplicaat
        assert rows[0].status is MemberStatus.approved
    finally:
        s.close()


def test_register_without_csrf_is_403(make_client, seed, SessionTest):
    client = make_client(None)
    csrf_token(client, f"/uitnodiging/{seed['token']}")  # mint sessie, geen token mee
    resp = client.post(
        f"/uitnodiging/{seed['token']}",
        data={"name": "X", "email": "x@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
    # Geen lid aangemaakt.
    from app.models import Member

    s = SessionTest()
    try:
        assert s.query(Member).filter(Member.email == "x@example.com").count() == 0
    finally:
        s.close()


def test_register_invalid_token_shows_expired(make_client, seed):
    client = make_client(None)
    token = csrf_token(client, f"/uitnodiging/{seed['token']}")
    resp = client.post(
        "/uitnodiging/dood-token",
        data={"name": "X", "email": "x@example.com", "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 410


def test_register_is_ip_rate_limited(make_client, seed, SessionTest):
    from app.config import settings
    from app.models import Member

    client = make_client(None)
    limit = settings.rate_limit_register_per_hour
    for i in range(limit):
        token = csrf_token(client, f"/uitnodiging/{seed['token']}")
        r = client.post(
            f"/uitnodiging/{seed['token']}",
            data={"name": "A", "email": f"flood{i}@example.com", "csrf_token": token},
            follow_redirects=False,
        )
        assert r.status_code == 303
    # De (limit+1)-e nieuwe inschrijving vanaf hetzelfde IP wordt geweigerd.
    token = csrf_token(client, f"/uitnodiging/{seed['token']}")
    blocked = client.post(
        f"/uitnodiging/{seed['token']}",
        data={"name": "A", "email": "over@example.com", "csrf_token": token},
        follow_redirects=False,
    )
    assert blocked.status_code == 429
    s = SessionTest()
    try:
        assert s.query(Member).filter(Member.email == "over@example.com").count() == 0
    finally:
        s.close()


# --- Admin ------------------------------------------------------------------ #
def test_admin_page_shows_active_link(make_client, seed):
    client = make_client(seed["admin"])
    resp = client.get("/admin/uitnodiging")
    assert resp.status_code == 200
    assert f"/uitnodiging/{seed['token']}" in resp.text


def test_admin_generate_revokes_old(make_client, seed, SessionTest):
    from app.models import GroupInvite

    client = make_client(seed["admin"])
    token = csrf_token(client, "/admin/uitnodiging")
    resp = client.post(
        "/admin/uitnodiging",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        active = s.query(GroupInvite).filter(GroupInvite.revoked.is_(False)).all()
        assert len(active) == 1  # precies één actieve
        assert active[0].token != seed["token"]  # de oude is geroteerd
        old = s.query(GroupInvite).filter(GroupInvite.token == seed["token"]).one()
        assert old.revoked is True
    finally:
        s.close()


def test_admin_route_requires_admin(make_client, seed, SessionTest):
    # Een gewoon (niet-admin) lid mag /admin/uitnodiging niet zien.
    from app.models import Member, MemberStatus

    s = SessionTest()
    plain = Member(email="lid@example.com", name="Lid", status=MemberStatus.approved)
    s.add(plain)
    s.commit()
    plain_id = plain.id
    s.close()

    client = make_client(plain_id)
    resp = client.get("/admin/uitnodiging", follow_redirects=False)
    assert resp.status_code == 403


def test_admin_route_anonymous_redirects_login(make_client, seed):
    client = make_client(None)
    resp = client.get("/admin/uitnodiging", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


# --------------------------------------------------------------------------- #
# Migratie-keten (0007)                                                        #
# --------------------------------------------------------------------------- #
@pytest.fixture
def migrated(monkeypatch):
    import tempfile
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from app.config import settings
    from sqlalchemy import create_engine

    root = Path(__file__).resolve().parents[1]
    db_path = Path(tempfile.mkstemp(suffix=".db", prefix="dwv-mig-inv-")[1])
    url = f"sqlite+pysqlite:///{db_path}"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    try:
        yield engine, cfg
    finally:
        engine.dispose()
        db_path.unlink(missing_ok=True)


def test_migration_chain_builds_group_invite(migrated):
    from sqlalchemy import inspect

    engine, _ = migrated
    insp = inspect(engine)
    assert "group_invite" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("group_invite")}
    assert {"id", "token", "expires_at", "created_by", "created_at", "revoked"} <= cols


def test_migration_downgrade_is_reversible(migrated):
    from alembic import command
    from sqlalchemy import inspect

    engine, cfg = migrated
    command.downgrade(cfg, "-1")
    insp = inspect(engine)
    assert "group_invite" not in insp.get_table_names()
    command.upgrade(cfg, "head")
    insp2 = inspect(engine)
    assert "group_invite" in insp2.get_table_names()
