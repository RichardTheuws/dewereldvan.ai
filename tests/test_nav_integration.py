"""Integratie-tests voor de kosmische hoofdnav op de speelveld-pagina's.

Bewijst dat het ad-hoc ``.c-head``-headerblok op de vier speelveld-templates
(``/leden``, ``/ideeen``, ``/roadmap``, ``/profiel/ai/bouwen``) is vervangen
door één include van ``_cosmic_nav.html`` — met de juiste ``aria-current``-
wayfinding per pagina, zónder de bestaande SEO (``/leden``) of de SSE-/slot-
structuur (``ai/live.html``) te breken.

Hermetisch (geen netwerk/Postgres): zelfde proven patroon als ``test_ideas.py``
— een wegwerp in-memory engine per test + ``current_member``-override stuurt de
exacte auth-state. ``/leden`` is publiek (anon), de overige drie zijn
``require_member`` (ingelogd, approved).
"""

from __future__ import annotations

import base64
import json

import itsdangerous
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests._route_helpers import make_route_engine

# Móet matchen met de SECRET_KEY die conftest vóór de app-import zet.
_SECRET = "test-secret-key-deterministic-0123456789abcdef"


def _session_cookie(data: dict) -> str:
    """Teken een sessie-cookie exact zoals Starlette's SessionMiddleware."""
    signer = itsdangerous.TimestampSigner(_SECRET)
    raw = base64.b64encode(json.dumps(data).encode("utf-8"))
    return signer.sign(raw).decode("utf-8")


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
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
    """Eén approved member (+ publiek profiel) en een approved admin."""
    from app.models import (
        Member,
        MemberRole,
        MemberStatus,
        Profile,
        Visibility,
    )

    s = SessionTest()
    member = Member(
        email="lid@example.com", name="Lid A", status=MemberStatus.approved
    )
    admin = Member(
        email="admin@example.com",
        name="Beheerder",
        status=MemberStatus.approved,
        role=MemberRole.admin,
    )
    s.add_all([member, admin])
    s.flush()
    # Publiek profiel zodat /leden ten minste één ster toont.
    profile = Profile(
        member_id=member.id,
        slug="lid-a",
        display_name="Lid A",
        visibility=Visibility.public,
    )
    s.add(profile)
    s.commit()
    ids = {"member": member.id, "admin": admin.id}
    s.close()
    return ids


@pytest.fixture
def make_client(route_engine, SessionTest):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app
    from app.models import Member

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
# 1. Nav aanwezig op elke speelveld-pagina                                    #
# --------------------------------------------------------------------------- #
def test_nav_present_on_leden(make_client, seed):
    """/leden (publiek) toont de kosmische hoofdnav i.p.v. de ad-hoc .c-head."""
    client = make_client(None)
    resp = client.get("/leden")
    assert resp.status_code == 200
    assert 'aria-label="Hoofdnavigatie"' in resp.text
    assert "cnav" in resp.text


def test_nav_present_on_ideeen(make_client, seed):
    client = make_client(seed["member"])
    resp = client.get("/ideeen")
    assert resp.status_code == 200
    assert 'aria-label="Hoofdnavigatie"' in resp.text
    assert "cnav" in resp.text


def test_nav_present_on_roadmap(make_client, seed):
    client = make_client(seed["member"])
    resp = client.get("/roadmap")
    assert resp.status_code == 200
    assert 'aria-label="Hoofdnavigatie"' in resp.text
    assert "cnav" in resp.text


def test_nav_present_on_ai_live(make_client, seed):
    client = make_client(seed["member"])
    resp = client.get("/profiel/ai/bouwen")
    assert resp.status_code == 200
    assert 'aria-label="Hoofdnavigatie"' in resp.text
    assert "cnav" in resp.text


# --------------------------------------------------------------------------- #
# 2. Active-state wayfinding (aria-current="page")                            #
# --------------------------------------------------------------------------- #
def test_active_state_leden(make_client, seed):
    """Op /leden draagt de Makers-link aria-current="page"."""
    client = make_client(None)
    resp = client.get("/leden")
    assert resp.status_code == 200
    # De Makers-link wijst naar /leden en is gemarkeerd als huidige pagina.
    assert 'href="/leden"' in resp.text
    assert 'aria-current="page"' in resp.text


def test_active_state_roadmap(make_client, seed):
    """Op /roadmap draagt de Roadmap-link aria-current="page"."""
    client = make_client(seed["member"])
    resp = client.get("/roadmap")
    assert resp.status_code == 200
    assert 'href="/roadmap"' in resp.text
    assert 'aria-current="page"' in resp.text


def test_active_state_ideeen(make_client, seed):
    client = make_client(seed["member"])
    resp = client.get("/ideeen")
    assert resp.status_code == 200
    assert 'href="/ideeen"' in resp.text
    assert 'aria-current="page"' in resp.text


# --------------------------------------------------------------------------- #
# 3. SEO van /leden blijft intact (nav vervangt _seo_head NIET)               #
# --------------------------------------------------------------------------- #
def test_leden_seo_intact(make_client, seed):
    """De publieke makerspagina blijft indexeerbaar; canonical/title intact."""
    client = make_client(None)
    resp = client.get("/leden")
    assert resp.status_code == 200
    # Indexeerbaar: geen noindex op de publieke showcase.
    assert "noindex" not in resp.text
    # _seo_head-artefacten aanwezig (canonical link + title).
    assert 'rel="canonical"' in resp.text
    assert "<title>" in resp.text


# --------------------------------------------------------------------------- #
# 4. ai/live.html ongemoeid — alleen de header is vervangen                   #
# --------------------------------------------------------------------------- #
def test_ai_live_sse_structure_intact(make_client, seed):
    """De SSE-/slot-structuur van de levende profielbouw blijft volledig staan."""
    client = make_client(seed["member"])
    resp = client.get("/profiel/ai/bouwen")
    assert resp.status_code == 200
    # SSE-materialisatie-container + invoer-dok bestaan nog ná de header-swap.
    assert 'id="materialisatie"' in resp.text
    assert 'hx-ext="sse"' in resp.text
    assert 'id="denkpaneel"' in resp.text
    assert 'hx-post="/profiel/ai/bericht"' in resp.text


# --------------------------------------------------------------------------- #
# 5. Admin-Beheer-link werkt overal (sessie-gebaseerd, niet alleen /ideeen)    #
# --------------------------------------------------------------------------- #
def test_admin_beheer_link_on_leden(make_client, seed):
    """De nav leest admin-state uit de sessie -> Beheer-link óók op /leden.

    Regressie-guard: voorheen las de nav een per-route ``is_admin``-context, dus
    de Beheer-link verscheen alleen op /ideeen. Nu spiegelt 'ie ``base.html``.
    """
    client = make_client(seed["admin"])
    client.cookies.set(
        "session", _session_cookie({"member_id": seed["admin"], "is_admin": True})
    )
    resp = client.get("/leden")
    assert resp.status_code == 200
    assert "Beheer" in resp.text
    assert "/admin/queue" in resp.text


def test_non_admin_sees_no_beheer_link(make_client, seed):
    """Een gewoon lid (geen is_admin in sessie) ziet geen Beheer-link (geen lek)."""
    client = make_client(seed["member"])
    client.cookies.set("session", _session_cookie({"member_id": seed["member"]}))
    resp = client.get("/leden")
    assert resp.status_code == 200
    assert "/admin/queue" not in resp.text
