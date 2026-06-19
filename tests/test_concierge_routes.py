"""Route-tests voor de Concierge (Fase 1) — hermetisch, geen netwerk.

Spiegelt het patroon van ``test_ai_profile_routes.py``: een wegwerp-engine per
test, ``current_member`` overridden naar de gewenste auth-staat, CSRF gemint via
een GET. Dekt: de instant-index (AVG-poort), nudge-dismiss-persist via de route,
en de founder-verhaal-route (alleen founder; opslag + flag-wis).
"""

from __future__ import annotations

import base64
import json
import re

import itsdangerous
import pytest
from app.models import (
    Base,
    ConciergeNudgeDismissal,
    Member,
    MemberStatus,
    Profile,
    Visibility,
)
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Zelfde SECRET_KEY als conftest injecteert (vóór de app-import). Nodig om een
# geldig getekend sessie-cookie te maken voor de founder-flag-tests.
_SECRET = "test-secret-key-deterministic-0123456789abcdef"


def _session_cookie(data: dict) -> str:
    signer = itsdangerous.TimestampSigner(_SECRET)
    raw = base64.b64encode(json.dumps(data).encode("utf-8"))
    return signer.sign(raw).decode("utf-8")


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
def make_client(route_engine, SessionTest):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app

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


def _csrf(client: TestClient) -> str:
    page = client.get("/login")
    assert page.status_code == 200
    m = re.search(r'name="csrf_token" value="([^"]+)"', page.text) or re.search(
        r"X-CSRF-Token&#34;: &#34;([^&]+)&#34;", page.text
    )
    assert m, "CSRF token not found"
    return m.group(1)


def _seed_public(SessionTest, *, name="Pub", tag="agents"):
    from app.services import profile_service

    s = SessionTest()
    member = Member(email=f"{name.lower()}@x.nl", name=name, status=MemberStatus.approved)
    s.add(member)
    s.flush()
    profile = Profile(
        member_id=member.id, slug=name.lower(), display_name=name,
        visibility=Visibility.public,
    )
    s.add(profile)
    s.flush()
    profile_service.set_tags(s, profile, tag)
    s.commit()
    mid = member.id
    s.close()
    return mid


def _seed_member(SessionTest, *, name="Lid", is_founder=False, email=None):
    s = SessionTest()
    member = Member(
        email=email or f"{name.lower()}@x.nl",
        name=name,
        status=MemberStatus.approved,
        is_founder=is_founder,
    )
    s.add(member)
    s.commit()
    mid = member.id
    s.close()
    return mid


# --------------------------------------------------------------------------- #
# Instant-index                                                               #
# --------------------------------------------------------------------------- #


def test_index_returns_public_only(make_client, SessionTest):
    _seed_public(SessionTest, name="Open", tag="agents")
    # Een besloten profiel mag NIET in de index verschijnen.
    s = SessionTest()
    m = Member(email="dicht@x.nl", name="Dicht", status=MemberStatus.approved)
    s.add(m)
    s.flush()
    s.add(Profile(member_id=m.id, slug="dicht", display_name="Dicht",
                  visibility=Visibility.members))
    s.commit()
    s.close()

    client = make_client(None)
    resp = client.get("/concierge/index")
    assert resp.status_code == 200
    data = resp.json()
    slugs = {it["slug"] for it in data["members"]}
    assert "open" in slugs
    assert "dicht" not in slugs


# --------------------------------------------------------------------------- #
# Nudge dismiss                                                               #
# --------------------------------------------------------------------------- #


def test_nudge_dismiss_persists_for_member(make_client, SessionTest):
    mid = _seed_member(SessionTest, name="Dismisser")
    client = make_client(mid)
    token = _csrf(client)
    resp = client.post(
        "/concierge/nudge/dismiss",
        data={"nudge_kind": "nieuwe_makers"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    s = SessionTest()
    row = s.scalar(
        select(ConciergeNudgeDismissal).where(
            ConciergeNudgeDismissal.member_id == mid
        )
    )
    assert row is not None
    assert row.nudge_kind == "nieuwe_makers"
    s.close()


def test_nudge_dismiss_anon_uses_cookie(make_client):
    client = make_client(None)
    token = _csrf(client)
    resp = client.post(
        "/concierge/nudge/dismiss",
        data={"nudge_kind": "nieuwe_makers"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_nudge_dismiss_empty_kind_400(make_client, SessionTest):
    mid = _seed_member(SessionTest, name="Empty")
    client = make_client(mid)
    token = _csrf(client)
    resp = client.post(
        "/concierge/nudge/dismiss",
        data={"nudge_kind": ""},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Founder ontstaansverhaal                                                    #
# --------------------------------------------------------------------------- #


def test_founder_story_saved(make_client, SessionTest):
    mid = _seed_member(
        SessionTest, name="Bart Ensink", is_founder=True, email="bart@x.nl"
    )
    client = make_client(mid)
    token = _csrf(client)
    resp = client.post(
        "/concierge/founder/verhaal",
        data={"verhaal": "We begonnen in een WhatsApp-groep."},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    s = SessionTest()
    member = s.get(Member, mid)
    assert member.origin_story == "We begonnen in een WhatsApp-groep."
    s.close()


def test_non_founder_story_forbidden(make_client, SessionTest):
    mid = _seed_member(SessionTest, name="Gewoon", is_founder=False)
    client = make_client(mid)
    token = _csrf(client)
    resp = client.post(
        "/concierge/founder/verhaal",
        data={"verhaal": "iets"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 403


def test_founder_story_anon_redirects(make_client):
    client = make_client(None)
    token = _csrf(client)
    resp = client.post(
        "/concierge/founder/verhaal",
        data={"verhaal": "iets"},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    # require_member → 303 naar /login voor een anonieme bezoeker.
    assert resp.status_code in (302, 303)


# --------------------------------------------------------------------------- #
# WIRING-tests: de echte naad tussen template, route en service               #
# (deze klasse bugs liet de proactieve laag / founder / navigatie DOOD)       #
# --------------------------------------------------------------------------- #


def _seed_member_with_tag(SessionTest, *, name, tag, email=None):
    """Een ingelogd lid mét profiel + tag (zodat tag-overlap-nudge kan vuren)."""
    from app.services import profile_service

    s = SessionTest()
    member = Member(
        email=email or f"{name.lower()}@x.nl",
        name=name,
        status=MemberStatus.approved,
    )
    s.add(member)
    s.flush()
    profile = Profile(
        member_id=member.id, slug=name.lower(), display_name=name,
        visibility=Visibility.members,
    )
    s.add(profile)
    s.flush()
    profile_service.set_tags(s, profile, tag)
    s.commit()
    mid = member.id
    s.close()
    return mid


# --- DIM-5: /concierge/index levert de route-tabel die het JS verwacht. ---
def test_index_includes_routes_table(make_client, SessionTest):
    """Het JS leest indexData.routes; de instant route-rijen moeten bestaan."""
    client = make_client(None)
    resp = client.get("/concierge/index")
    assert resp.status_code == 200
    data = resp.json()
    assert "routes" in data, "routes-tabel ontbreekt (instant route-rijen zouden DOOD zijn)"
    labels = {r["label"] for r in data["routes"]}
    assert {"Leden", "Ideeën", "Roadmap"} <= labels
    for r in data["routes"]:
        assert "url" in r and "keywords" in r and isinstance(r["keywords"], list)
    # Anoniem: geen "Mijn profiel".
    assert "Mijn profiel" not in labels


def test_index_routes_include_profile_for_member(make_client, SessionTest):
    mid = _seed_member(SessionTest, name="Ingelogd")
    client = make_client(mid)
    resp = client.get("/concierge/index")
    labels = {r["label"] for r in resp.json()["routes"]}
    assert "Mijn profiel" in labels


def test_index_members_use_name_key(make_client, SessionTest):
    """Het JS leest m.name (niet display_name); de sleutel moet 'name' zijn."""
    _seed_public(SessionTest, name="Naamlid", tag="agents")
    client = make_client(None)
    resp = client.get("/concierge/index")
    member_rows = resp.json()["members"]
    assert member_rows
    assert all("name" in m for m in member_rows)
    assert any(m["name"] == "Naamlid" for m in member_rows)


# --- B1: dismiss met de ECHTE template-hx-vals-payload (geen handgeschreven veld). ---
def _render_nudge_html(nudge_kind: str) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    nudge = {"kind": nudge_kind, "text": "x", "action": "doe", "url": "/leden"}
    return env.get_template("concierge/_nudge.html").render(nudge=nudge)


def test_dismiss_uses_template_hx_vals_payload(make_client, SessionTest):
    """Render _nudge.html, trek de hx-vals eruit en post die → moet 200 zijn.

    Dit dekt de echte naad: de veldnaam in de template MOET matchen met wat de
    route uit het formulier leest. Een mismatch gaf eerder een 400.
    """
    html = _render_nudge_html("nieuwe_makers")
    m = re.search(r"hx-vals='([^']+)'", html)
    assert m, "hx-vals niet gevonden in _nudge.html"
    vals = json.loads(m.group(1))
    # De payload draagt precies één veld; dat is de naam die de route leest.
    assert "nudge_kind" in vals, f"template-veldnaam mismatch: {list(vals)}"
    assert vals["nudge_kind"] == "nieuwe_makers"

    mid = _seed_member(SessionTest, name="HxVals")
    client = make_client(mid)
    token = _csrf(client)
    resp = client.post(
        "/concierge/nudge/dismiss",
        data=vals,
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    # En het is echt gepersisteerd onder de juiste kind.
    s = SessionTest()
    row = s.scalar(
        select(ConciergeNudgeDismissal).where(
            ConciergeNudgeDismissal.member_id == mid
        )
    )
    assert row is not None and row.nudge_kind == "nieuwe_makers"
    s.close()


# --- B2: GET /concierge/nudge levert het gerenderde fragment (of leeg). ---
def test_nudge_endpoint_empty_when_no_trigger(make_client, SessionTest):
    """Geen sterke trigger (lege DB, geen viewer) → leeg fragment, geen vulling."""
    client = make_client(None)
    resp = client.get("/concierge/nudge")
    assert resp.status_code == 200
    assert resp.text.strip() == ""


def test_nudge_endpoint_renders_fragment_for_member(make_client, SessionTest):
    """Een lid met tag-overlap krijgt een gerenderd _nudge.html-fragment terug."""
    # Een andere publieke maker met dezelfde tag → tag-overlap-nudge.
    _seed_public(SessionTest, name="Mark", tag="voice-agents")
    mid = _seed_member_with_tag(SessionTest, name="Viewer", tag="voice-agents")
    client = make_client(mid)
    resp = client.get("/concierge/nudge")
    assert resp.status_code == 200
    assert "concierge-nudge" in resp.text
    # De dismiss-knop draagt de juiste veldnaam (B1-naad ook hier).
    assert "nudge_kind" in resp.text
    assert "tag_overlap:mark" in resp.text


# --- B3: founder-welkomst — canonical sessie-sleutel + kind overal gelijk. ---
def test_nudge_endpoint_founder_welcome(make_client, SessionTest):
    """Met de founder-flag + een herkende founder → de founder-welkomst-nudge."""
    mid = _seed_member(
        SessionTest, name="Bart Ensink", is_founder=True, email="bart@x.nl"
    )
    client = make_client(mid)
    # Zet de canonical sessie-flag via een getekend cookie.
    client.cookies.set("session", _session_cookie({"concierge_founder_welcome": True}))
    resp = client.get("/concierge/nudge")
    assert resp.status_code == 200
    # Canonical kind 'founder_welcome' overal (template-class + dismiss-payload).
    assert "founder_welcome" in resp.text
    assert "concierge-nudge--founder" in resp.text


def test_nudge_endpoint_no_founder_without_flag(make_client, SessionTest):
    """Zonder de flag krijgt een founder geen welkomst-nudge opgedrongen."""
    mid = _seed_member(
        SessionTest, name="Hendrik van Zwol", is_founder=True, email="h@x.nl"
    )
    client = make_client(mid)
    resp = client.get("/concierge/nudge")
    # Geen flag → geen founder-welkomst (en lege DB → geen andere trigger).
    assert "founder_welcome" not in resp.text


def test_founder_dismiss_clears_session_flag(make_client, SessionTest):
    """Dismiss van de founder-nudge wist de eenmalige sessie-flag (geen herhaling)."""
    mid = _seed_member(
        SessionTest, name="Bart Ensink", is_founder=True, email="bart2@x.nl"
    )
    client = make_client(mid)
    client.cookies.set("session", _session_cookie({"concierge_founder_welcome": True}))
    token = _csrf(client)
    # De founder-nudge is nu zichtbaar...
    assert "founder_welcome" in client.get("/concierge/nudge").text
    # ...dismiss met de canonical kind...
    resp = client.post(
        "/concierge/nudge/dismiss",
        data={"nudge_kind": "founder_welcome"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    # ...en daarna is de flag weg: de welkomst komt niet meer terug.
    assert "founder_welcome" not in client.get("/concierge/nudge").text


# --- M1: card-rendering gebruikt een EIGEN sessie (niet de request-db). ---
def test_card_render_uses_separate_session(make_client, SessionTest, monkeypatch):
    """Bewijst dat de drain-thread kaarten in een aparte SessionLocal rendert.

    De tool-loop (_run) draait op de request-db in de threadpool; als de
    drain-thread diezelfde Session zou queryen is dat niet thread-safe. We
    monkeypatchen SessionLocal in de router en bewijzen dat card-rendering 'm
    opent (en dus NIET de request-db deelt), terwijl de grounde kaart toch
    materialiseert.
    """
    import anthropic
    from app.routers import concierge as concierge_router

    from tests.test_concierge import FakeAnthropicLoop, _Block

    # Een echte publieke maker zodat de slug → een gegronde kaart wordt.
    _seed_public(SessionTest, name="Kaartlid", tag="agents")

    # Tel hoe vaak de router zijn EIGEN SessionLocal opent voor kaart-rendering.
    opened: list[int] = []
    real_session_local = SessionTest

    def _counting_session_local():
        opened.append(1)
        return real_session_local()

    monkeypatch.setattr(concierge_router, "SessionLocal", _counting_session_local)

    # Fake Anthropic: search_members → 'kaartlid' → één card-signaal.
    tool_use = _Block(
        type="tool_use", id="t1", name="search_members", input={"tag": "agents"}
    )
    fake = FakeAnthropicLoop([
        {"deltas": [], "stop_reason": "tool_use", "content": [tool_use]},
        {"deltas": ["Eén."], "stop_reason": "end_turn",
         "content": [{"type": "text", "text": "Eén."}]},
    ])
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: fake)

    client = make_client(None)
    token = _csrf(client)
    # Parkeer een vraag (POST /bericht) en consumeer de stream.
    client.post(
        "/concierge/bericht",
        data={"message": "wie bouwt agents?"},
        headers={"X-CSRF-Token": token},
    )
    resp = client.get("/concierge/stream")
    assert resp.status_code == 200
    body = resp.text
    # De gegronde kaart materialiseerde (grounding-poort bleef intact)...
    assert "event: card" in body
    assert "Kaartlid" in body
    # ...en is gerenderd via een aparte SessionLocal (niet de request-db).
    assert opened, "card-rendering opende GEEN eigen sessie (deelt de request-db!)"


def test_founder_session_key_canonical_in_auto_open(make_client, SessionTest):
    """Het oppervlak auto-opent op de canonical sleutel concierge_founder_welcome."""
    mid = _seed_member(
        SessionTest, name="Bart Ensink", is_founder=True, email="bart3@x.nl"
    )
    client = make_client(mid)
    client.cookies.set("session", _session_cookie({"concierge_founder_welcome": True}))
    resp = client.get("/leden")
    assert resp.status_code == 200
    # data-auto-open verschijnt alléén als de canonical sleutel gezet is.
    assert 'data-auto-open="1"' in resp.text


# --------------------------------------------------------------------------- #
# Fase 3: één shell — nav verbergt het sectie-menu voor een ingelogd lid       #
# --------------------------------------------------------------------------- #


def test_anon_sees_full_nav_no_fallback(make_client, SessionTest):
    """Anoniem op een klassieke pagina → de volledige crawlbare voordeur-nav,
    geen footer-fallback (dat is het shell-vangnet voor leden)."""
    client = make_client(None)
    resp = client.get("/leden")
    assert resp.status_code == 200
    # Volledige nav: sectie-links + login/register.
    assert 'href="/agenda"' in resp.text
    assert 'href="/roadmap"' in resp.text
    assert 'href="/register"' in resp.text
    assert 'href="/login"' in resp.text
    # Geen footer-fallback voor anoniem.
    assert "canvas-fallback__toggle" not in resp.text


def test_member_nav_is_single_shell(make_client, SessionTest):
    """Ingelogd lid op een klassieke pagina → GEEN sectie-menu/login in de nav,
    wél de concierge-ingang; en de footer-fallback is het a11y/no-JS-vangnet."""
    mid = _seed_member(SessionTest, name="Lid", email="shell@x.nl")
    client = make_client(mid)
    client.cookies.set("session", _session_cookie({"member_id": mid}))
    resp = client.get("/leden")
    assert resp.status_code == 200
    # De concierge-ingang blijft (de shell).
    assert "cnav__concierge" in resp.text
    # Geen voordeur-nav meer: geen sectie-links of login/register in de nav.
    assert "cnav__links" not in resp.text
    assert 'href="/register"' not in resp.text
    assert 'href="/login"' not in resp.text
    # De footer-fallback (echte links, no-JS-vangnet) IS aanwezig.
    assert "canvas-fallback__toggle" in resp.text
    assert 'href="/agenda"' in resp.text  # via de fallback bereikbaar
    assert 'href="/profiel/verbind"' in resp.text


def test_admin_keeps_beheer_in_shell_nav(make_client, SessionTest):
    """Een admin houdt de Beheer-link in de minimale shell-nav (queue-toegang)."""
    s = SessionTest()
    from app.models import MemberRole

    m = Member(
        email="admin@x.nl", name="Admin", status=MemberStatus.approved,
        role=MemberRole.admin,
    )
    s.add(m)
    s.commit()
    mid = m.id
    s.close()
    client = make_client(mid)
    client.cookies.set(
        "session", _session_cookie({"member_id": mid, "is_admin": True})
    )
    resp = client.get("/leden")
    assert resp.status_code == 200
    assert 'href="/admin/queue"' in resp.text
    assert "cnav__concierge" in resp.text


def test_canvas_has_single_fallback(make_client, SessionTest):
    """Op de canvas (root voor een ingelogd lid) staat de footer-fallback precies
    één keer — _concierge.html voegt 'm daar NIET nog eens toe (host_owned)."""
    mid = _seed_member(SessionTest, name="Canvas", email="canvas@x.nl")
    client = make_client(mid)
    client.cookies.set("session", _session_cookie({"member_id": mid}))
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.text.count('id="canvas-fallback-toggle"') == 1
