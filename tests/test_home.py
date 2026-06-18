"""De kosmische voordeur (/) — anon + ingelogd render, signaal-/preview-gating,
SEO-intact en regressie-guards tegen het oude lichte thema.

De ``/``-route leest de login-state direct uit ``request.session`` (niet via
``current_member``), dus we zetten een echt getekende sessie-cookie (zoals
Starlette's SessionMiddleware) i.p.v. een dependency-override. Een wegwerp-engine
per test houdt de geseede profielen hermetisch.
"""

from __future__ import annotations

import base64
import json

import itsdangerous
import pytest
from app.models import Member, MemberRole, MemberStatus, Profile, Visibility
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tests._route_helpers import make_route_engine

# Móet matchen met de SECRET_KEY die conftest vóór de app-import zet.
_SECRET = "test-secret-key-deterministic-0123456789abcdef"


def _session_cookie(data: dict) -> str:
    """Teken een sessie-cookie exact zoals Starlette's SessionMiddleware."""
    signer = itsdangerous.TimestampSigner(_SECRET)
    raw = base64.b64encode(json.dumps(data).encode("utf-8"))
    return signer.sign(raw).decode("utf-8")


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
def client(route_engine, SessionTest):
    from app.db import get_db
    from app.main import app

    def _override_get_db():
        s = SessionTest()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.clear()


def _seed_public(SessionTest, n: int) -> None:
    """Maak ``n`` publieke, goedgekeurde profielen (constellatie-leden)."""
    with SessionTest() as s:
        for i in range(n):
            m = Member(
                email=f"maker{i}@example.com",
                name=f"Maker {i}",
                status=MemberStatus.approved,
            )
            s.add(m)
            s.flush()
            s.add(
                Profile(
                    member_id=m.id,
                    slug=f"maker-{i}",
                    display_name=f"Maker {i}",
                    visibility=Visibility.public,
                )
            )
        s.commit()


# --------------------------------------------------------------------------- #
# Anon render                                                                  #
# --------------------------------------------------------------------------- #
def test_home_anon_renders_cosmic(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    # Kosmisch document + nav + levend sterrenveld.
    assert 'class="cosmic"' in body
    assert 'aria-label="Hoofdnavigatie"' in body
    assert 'id="stars"' in body
    # Anon-CTA's en deuren.
    assert "Word lid" in body
    assert "/leden" in body
    # Regressie-guard: geen lichte-thema-restanten.
    assert "text-slate-900" not in body
    assert "De wereld van ons" not in body


def test_home_anon_seo_indexable(client):
    resp = client.get("/")
    assert resp.status_code == 200
    # Indexeerbaar: geen noindex-meta.
    assert "noindex" not in resp.text


def test_home_canonical_not_empty(client):
    """SEO-regressie-guard: de voordeur emit geen lege canonical/og:url."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'rel="canonical" href=""' not in resp.text
    assert 'property="og:url" content=""' not in resp.text


def test_home_admin_sees_beheer_link(client, SessionTest):
    """Admin-state uit de sessie -> de nav toont de Beheer-link (overal, niet alleen
    op /ideeen). Bewijst de sessie-gebaseerde admin-check in _cosmic_nav.html."""
    with SessionTest() as s:
        m = Member(
            email="admin@example.com",
            name="Beheer",
            status=MemberStatus.approved,
            role=MemberRole.admin,
        )
        s.add(m)
        s.commit()
        member_id = m.id

    client.cookies.set(
        "session", _session_cookie({"member_id": member_id, "is_admin": True})
    )
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Beheer" in resp.text
    assert "/admin/queue" in resp.text


# --------------------------------------------------------------------------- #
# Ingelogd render                                                             #
# --------------------------------------------------------------------------- #
def test_home_logged_in_renders_member_doorway(client, SessionTest):
    with SessionTest() as s:
        m = Member(
            email="lid@example.com", name="Ingelogd Lid", status=MemberStatus.approved
        )
        s.add(m)
        s.commit()
        member_id = m.id

    client.cookies.set("session", _session_cookie({"member_id": member_id}))
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "Naar mijn profiel" in body
    assert "/profiel/ai/bouwen" in body
    assert "Ontdek de makers" in body
    # Ingelogd toont geen "Word lid"-CTA op de hero.
    assert "Welkom in de wereld." in body


# --------------------------------------------------------------------------- #
# Signaal-gating (makers-getal)                                               #
# --------------------------------------------------------------------------- #
def test_home_signal_hidden_with_zero_makers(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "MAKERS" not in resp.text


def test_home_signal_shown_with_makers(client, SessionTest):
    _seed_public(SessionTest, 1)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "1 MAKERS" in resp.text


# --------------------------------------------------------------------------- #
# Preview-gating (constellatie-mini's in de Makers-kaart)                      #
# --------------------------------------------------------------------------- #
def test_home_preview_hidden_below_three(client, SessionTest):
    _seed_public(SessionTest, 2)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "home-gate__stars" not in resp.text


def test_home_preview_shown_at_three(client, SessionTest):
    _seed_public(SessionTest, 3)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "home-gate__stars" in resp.text
