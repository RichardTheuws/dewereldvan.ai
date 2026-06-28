"""Admin ledenoverzicht (/admin/leden) — toont iedereen incl. status + laatst-ingelogd.

Gate: alleen admins (anon → redirect naar login, gewoon lid → 403). De pagina lijst
álle leden ongeacht status, met hun profiel-zichtbaarheid en laatste login.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models import (
    Member,
    MemberRole,
    MemberStatus,
    Profile,
    Visibility,
)
from app.models import Base
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine():
    """Function-scoped in-memory engine — verse DB per test (echte commits, geen
    transactie-rollback-isolatie), zodat herhaalde seeds niet op elkaar botsen."""
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


def _seed(engine) -> int:
    """Zaai een admin + drie leden (openbaar / besloten / pending) en geef admin-id."""
    SessionTest = sessionmaker(bind=engine, autoflush=False, future=True)
    s = SessionTest()

    admin = Member(
        email="beheer@example.com", name="Beheer Baas",
        status=MemberStatus.approved, role=MemberRole.admin,
        last_login_at=datetime(2026, 6, 28, 11, 5, tzinfo=UTC).replace(tzinfo=None),
    )
    s.add(admin)

    openbaar = Member(
        email="wouter@example.com", name="Wouter Openbaar",
        status=MemberStatus.approved,
        last_login_at=datetime(2026, 6, 28, 10, 5, tzinfo=UTC).replace(tzinfo=None),
    )
    s.add(openbaar)
    s.flush()
    s.add(Profile(
        member_id=openbaar.id, slug="wouter", display_name="Wouter Openbaar",
        visibility=Visibility.public,
    ))

    besloten = Member(
        email="frank@example.com", name="Frank Besloten",
        status=MemberStatus.approved,
    )
    s.add(besloten)
    s.flush()
    s.add(Profile(
        member_id=besloten.id, slug="frank", display_name="Frank Besloten",
        visibility=Visibility.members,
    ))

    # pending, nog géén profiel, nooit ingelogd
    s.add(Member(
        email="twijfel@example.com", name="Twijfel Geval",
        status=MemberStatus.pending,
    ))

    s.commit()
    admin_id = admin.id
    s.close()
    return admin_id


@pytest.fixture
def make_admin_client(engine):
    """Factory: een TestClient waarbij ``current_member`` een gekozen lid teruggeeft
    (of None voor anoniem), met de gedeelde test-engine als DB."""
    from app.db import get_db
    from app.deps import current_member
    from app.main import app

    SessionTest = sessionmaker(bind=engine, autoflush=False, future=True)

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    def _factory(member_id: int | None):
        def _override_current_member(db: Session = Depends(get_db)):
            return db.get(Member, member_id) if member_id is not None else None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def test_overview_lists_everyone_with_status_and_last_login(make_admin_client, engine):
    admin_id = _seed(engine)
    client = make_admin_client(admin_id)

    resp = client.get("/admin/leden")
    assert resp.status_code == 200
    body = resp.text

    # Iedereen staat erin, ongeacht status.
    for naam in ("Wouter Openbaar", "Frank Besloten", "Twijfel Geval", "Beheer Baas"):
        assert naam in body

    # Zichtbaarheid wordt onderscheiden.
    assert "openbaar" in body
    assert "besloten" in body
    assert "geen profiel" in body

    # Status-labels + laatst-ingelogd (datum van de seed) zijn zichtbaar.
    assert "in de wacht" in body  # de pending
    assert "28-06 10:05" in body  # Wouters laatste login
    assert "admin" in body


def test_overview_requires_admin(make_admin_client, engine):
    _seed(engine)
    # Een gewoon (niet-admin) lid → 403.
    SessionTest = sessionmaker(bind=engine, autoflush=False, future=True)
    s = SessionTest()
    lid = s.scalar(select(Member).where(Member.email == "wouter@example.com"))
    lid_id = lid.id
    s.close()

    client = make_admin_client(lid_id)
    resp = client.get("/admin/leden")
    assert resp.status_code == 403


def test_overview_anonymous_redirects_to_login(make_admin_client, engine):
    _seed(engine)
    client = make_admin_client(None)
    resp = client.get("/admin/leden", follow_redirects=False)
    assert resp.status_code in (302, 303)
