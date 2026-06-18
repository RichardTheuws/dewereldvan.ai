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


def test_home_favicon_and_og_image(client):
    """D2/D3 — de voordeur linkt de favicon + theme-color en emit de OG-kaart
    met het kosmische og-default beeld (publieke unfurl)."""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    # Favicon-partial + theme-color in de <head>.
    assert "/static/favicon.svg" in body
    assert 'name="theme-color"' in body
    # OG-beeld op de publieke voordeur (indexeerbaar → og:image toegestaan).
    assert "/static/og-default.png" in body
    assert 'property="og:image"' in body


def test_static_assets_served(client):
    """D1/D3 — favicon (svg+ico) en og-default worden door StaticFiles geserveerd."""
    for path, ctype in (
        ("/static/favicon.svg", "image/svg+xml"),
        ("/static/favicon.ico", "image/"),
        ("/static/og-default.png", "image/png"),
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert ctype in r.headers.get("content-type", ""), path


def test_home_admin_keeps_beheer_access(client, SessionTest):
    """Agent-Shell: een approved admin landt op de canvas (geen hoofdnav), maar
    houdt operationeel toegang tot de goedkeur-queue via de footer-fallback —
    sessie-gebaseerde admin-check in concierge/_footer_fallback.html."""
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
    # Dual-shell: de agent-canvas, geen klassieke hoofdnav.
    assert 'id="concierge-materialisatie"' in resp.text
    assert 'aria-label="Hoofdnavigatie"' not in resp.text
    # Operationeel vangnet: de Beheer-link blijft bereikbaar.
    assert "Beheer" in resp.text
    assert "/admin/queue" in resp.text


# --------------------------------------------------------------------------- #
# Ingelogd render                                                             #
# --------------------------------------------------------------------------- #
def test_home_approved_member_lands_in_canvas(client, SessionTest):
    """Agent-Shell (dual-shell): een ingelogd, GOEDGEKEURD lid landt direct in de
    levende agent-canvas — geen hoofdnav/menu, login-gated (noindex), met het
    zichtbare invoerveld en de SSE-host. Vervangt de oude index-voordeur."""
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
    # De canvas-shell: SSE-host mét hx-ext, geen hoofdnav, login-gated.
    assert 'id="concierge-materialisatie"' in body
    assert 'hx-ext="sse"' in body
    assert 'aria-label="Hoofdnavigatie"' not in body
    assert "noindex" in body
    # Het primaire, zichtbare veld + een eenvoudige welkomst (geen "Word lid").
    assert 'id="canvas-form"' in body
    assert "Welkom" in body
    assert "Word lid" not in body


def test_home_pending_member_gets_public_doorway(client, SessionTest):
    """Dual-shell-grens: een nog niet goedgekeurd (pending) lid krijgt NIET de
    canvas maar de klassieke, crawlbare voordeur (zonder KeyError op de context)."""
    with SessionTest() as s:
        m = Member(
            email="wacht@example.com", name="Wachtend", status=MemberStatus.pending
        )
        s.add(m)
        s.commit()
        member_id = m.id

    client.cookies.set("session", _session_cookie({"member_id": member_id}))
    resp = client.get("/")
    assert resp.status_code == 200
    # De voordeur, niet de canvas: het zichtbare canvas-veld (#canvas-form) is
    # canvas-only; de hoofdnav hoort juist bij de voordeur. (De verborgen
    # concierge-overlay-host zit op élke pagina, dus die is geen discriminator.)
    assert 'id="canvas-form"' not in resp.text
    assert 'aria-label="Hoofdnavigatie"' in resp.text


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
    # D4: enkelvoud bij precies 1 maker (geen "1 MAKERS").
    assert "1 MAKER" in resp.text
    assert "1 MAKERS" not in resp.text


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
