"""Route-smoke voor de 'bekijk-als-bezoeker'-preview (GET /profiel/voorbeeld).

De preview toont de eigenaar exact wat een bezoeker ziet, vóór publiceren:
- require_member-guard (anon/pending → /login).
- Rendert profiles/view.html met is_owner=False (bezoekers-nav, geen eigenaar-nav).
- Altijd noindex; nooit OG/JSON-LD (geen lek in zoekmachines/unfurls).
- De preview-chrome past zich aan op de live-zichtbaarheid (chip + actie).

Een wegwerp-engine houdt de gecommitte rijen weg bij de rollback-geïsoleerde
``db``-fixture van zustertests (zelfde patroon als test_ai_profile_routes).
"""

from __future__ import annotations

import pytest
from app.models import Base, Member, MemberStatus, Visibility
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
    """Een approved + een pending lid in de wegwerp-engine."""
    s = SessionTest()
    approved = Member(
        email="kijker@example.com", name="Nova Maker", status=MemberStatus.approved
    )
    pending = Member(
        email="wacht@example.com", name="Wachtend", status=MemberStatus.pending
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


def _set_public(SessionTest, member_id: int) -> None:
    """Maak het profiel van een lid openbaar (met consent), via de service."""
    from app.services.profile_service import get_or_create_profile
    from app.services.visibility import change_visibility

    s = SessionTest()
    try:
        member = s.get(Member, member_id)
        profile = get_or_create_profile(s, member)
        change_visibility(s, profile, Visibility.public, actor=member, consent=True)
        s.commit()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Guard                                                                        #
# --------------------------------------------------------------------------- #
def test_preview_anonymous_redirects_to_login(make_client):
    client = make_client(None)
    resp = client.get("/profiel/voorbeeld", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_preview_pending_member_redirects(make_client, seed):
    client = make_client(seed["pending"])
    resp = client.get("/profiel/voorbeeld", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


# --------------------------------------------------------------------------- #
# Approved owner — members-only (nog niet gepubliceerd)                        #
# --------------------------------------------------------------------------- #
def test_preview_members_only_shows_visitor_view_and_chrome(make_client, seed):
    client = make_client(seed["approved"])
    resp = client.get("/profiel/voorbeeld")
    assert resp.status_code == 200

    # De preview-chrome staat er, met de "nog niet openbaar"-staat.
    assert "preview-frame" in resp.text
    assert "Voorbeeld" in resp.text
    assert "Nog niet openbaar" in resp.text
    assert "Maak openbaar" in resp.text
    assert 'class="cosmic preview-on"' in resp.text

    # De inhoud van het profiel rendert (bezoekers-ervaring).
    assert "Nova Maker" in resp.text

    # is_owner=False → bezoekers-nav, niet de eigenaar-nav.
    assert "Bewerken met AI" not in resp.text
    assert 'href="/leden"' in resp.text

    # Een preview mag nooit indexeerbaar zijn / geen unfurl-data lekken.
    assert 'name="robots" content="noindex"' in resp.text
    assert "application/ld+json" not in resp.text
    assert 'property="og:image"' not in resp.text


# --------------------------------------------------------------------------- #
# Approved owner — al openbaar (progress-bewuste chrome)                       #
# --------------------------------------------------------------------------- #
def test_preview_public_profile_shows_openbaar_state(make_client, seed, SessionTest):
    _set_public(SessionTest, seed["approved"])
    client = make_client(seed["approved"])
    resp = client.get("/profiel/voorbeeld")
    assert resp.status_code == 200

    # Reeds openbaar → geen "maak openbaar"-actie, wél de openbaar-chip + beheer.
    assert "Openbaar" in resp.text
    assert "Maak openbaar" not in resp.text
    assert "Zichtbaarheid" in resp.text
    # Preview blijft noindex, óók als het profiel live openbaar is.
    assert 'name="robots" content="noindex"' in resp.text
