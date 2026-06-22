"""Render-smoke for the kosmiseerde forms-pagina's (TEAM-FORMS: F1 + F4).

Bevestigt dat /profiel/bewerken (lid) en /admin/queue (admin) als standalone
cosmic-documenten renderen, met alle htmx-haken (offering/need-lijsten,
profiel-status, member-acties) intact en zonder Tailwind-emerald-resten.

Hergebruikt het hermetische throwaway-engine + current_member-override-patroon
uit test_ai_profile_routes.py (geen Postgres, geen netwerk).
"""

from __future__ import annotations

import pytest
from app.models import Base
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def route_engine():
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


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(
        bind=route_engine, autoflush=False, autocommit=False, future=True
    )


@pytest.fixture
def seed(SessionTest):
    """An approved member (with profile) + a pending member awaiting approval."""
    from app.models import Member, MemberStatus

    s = SessionTest()
    approved = Member(
        email="builder@example.com", name="Bouwer", status=MemberStatus.approved
    )
    pending = Member(
        email="wachtend@example.com", name="Wachtend", status=MemberStatus.pending
    )
    s.add_all([approved, pending])
    s.commit()
    ids = {"approved": approved.id, "pending": pending.id}
    s.close()
    return ids


@pytest.fixture
def make_client(route_engine, SessionTest):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app
    from app.models import Member
    from fastapi import Depends
    from sqlalchemy.orm import Session

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
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# F1 — profiel bewerken                                                        #
# --------------------------------------------------------------------------- #
def test_edit_page_is_cosmic_with_htmx_hooks_intact(make_client, seed):
    """T4: edit-pagina rendert cosmic + alle swap-doelen + CSRF aanwezig."""
    client = make_client(seed["approved"])
    resp = client.get("/profiel/bewerken")
    assert resp.status_code == 200
    body = resp.text
    # Standalone cosmic document, geen lichte base.html-resten.
    assert 'class="cosmic"' in body
    assert "text-slate-900" not in body
    assert "bg-emerald-600" not in body
    # htmx swap-doelen blijven exact.
    assert 'id="offering-list"' in body
    assert 'id="need-list"' in body
    assert 'id="profiel-status"' in body
    # Hoofdform houdt zijn klassieke hidden CSRF-veld (geen htmx).
    assert 'name="csrf_token"' in body
    # Body draagt de hx-headers CSRF voor de htmx-secties.
    assert "X-CSRF-Token" in body
    # Kern-velden + htmx-endpoints overeind.
    assert 'name="display_name"' in body
    assert 'hx-post="/profiel/offering"' in body
    assert 'hx-post="/profiel/need"' in body
    assert 'hx-post="/profiel/zichtbaarheid"' in body
    assert 'action="/profiel/bewerken"' in body


# --------------------------------------------------------------------------- #
# F4 — admin aanmeldingen-queue                                               #
# --------------------------------------------------------------------------- #
def test_admin_queue_is_cosmic_and_lists_pending(make_client, seed):
    """T5: queue rendert cosmic; openstaande aanmelding krijgt zijn actie-knoppen."""
    # Promote the approved member to admin so require_admin passes.
    from app.deps import require_admin
    from app.main import app

    client = make_client(seed["approved"])

    def _override_require_admin():
        return None

    app.dependency_overrides[require_admin] = _override_require_admin
    try:
        resp = client.get("/admin/queue")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert resp.status_code == 200
    body = resp.text
    assert 'class="cosmic"' in body
    assert "text-slate-900" not in body
    assert "Aanmeldingen" in body
    # Het wachtende lid + zijn acties staan erin.
    assert "Wachtend" in body
    assert "/approve" in body
    assert "/reject" in body
    # Pivot Fase A: de queue heet welkom / markeert spam — geen "weiger"-oordeel.
    assert "Welkom heten" in body
    assert "Markeer als spam" in body
    assert "Weigeren" not in body
