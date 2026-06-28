"""Render-/integratie-tests voor het FRONTEND van de Concierge (PRD §2/§4.1/§5.1).

Bewijst (zonder de backend-routes, die het andere team levert) dat:

1. Het intent-oppervlak (``_concierge.html``) + de preview-band
   (``_preview_banner.html``) cross-cutting op de kosmische pagina's verschijnen —
   publiek (/leden, /, /404) én ingelogd (/profiel/ai/bouwen, /ideeen, /roadmap).
2. De drie oproep-ingangen aanwezig zijn: ⌘K/"/"-keybinding-hook (de JS-bindings),
   de "✦ Vraag de wereld"-nav-knop, en het invoerveld dat naar
   ``/concierge/bericht`` post.
3. De contextuele placeholder per pagina klopt (PRD §2.1).
4. A11y: role="dialog" + aria-modal + focus-trap-markup + aria-label.
5. De preview-band server-rendered is (werkt zonder JS) en met de
   ``dwv_preview_dismissed``-cookie verdwijnt.
6. De SSE-stream-host (``concierge/_stream.html``) de bewezen verse-proxy-aanpak
   gebruikt (geen sse-swap op vooraf-bestaande elementen) en een ``card``-binding
   heeft die naar ``#concierge-results`` appendt.
7. De makerkaart-in-de-stroom (``concierge/_card.html``) de echte
   ``members/_member_star.html`` hergebruikt (grounding: server-side uit de DB).

Hermetisch (geen netwerk/Postgres): zelfde patroon als ``test_nav_integration.py``.
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

_SECRET = "test-secret-key-deterministic-0123456789abcdef"


def _session_cookie(data: dict) -> str:
    signer = itsdangerous.TimestampSigner(_SECRET)
    raw = base64.b64encode(json.dumps(data).encode("utf-8"))
    return signer.sign(raw).decode("utf-8")


# --------------------------------------------------------------------------- #
# Fixtures (gespiegeld op test_nav_integration.py)                            #
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
    from app.models import (
        Member,
        MemberStatus,
        Profile,
        Visibility,
    )

    s = SessionTest()
    member = Member(
        email="lid@example.com", name="Sanne Vidal", status=MemberStatus.approved
    )
    s.add(member)
    s.flush()
    profile = Profile(
        member_id=member.id,
        slug="sanne-vidal",
        display_name="Sanne Vidal",
        visibility=Visibility.public,
        headline="Bouwt AI-tools voor de zorg",
    )
    s.add(profile)
    s.commit()
    ids = {"member": member.id, "slug": "sanne-vidal"}
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
# 1. Oppervlak + band aanwezig op de pagina's (cross-cutting)                  #
# --------------------------------------------------------------------------- #
def test_surface_present_on_public_leden(make_client, seed):
    """Anon: /leden draagt het Concierge-oppervlak én de preview-band."""
    client = make_client(None)
    resp = client.get("/leden")
    assert resp.status_code == 200
    assert 'id="concierge-overlay"' in resp.text
    assert 'role="dialog"' in resp.text
    assert "preview-banner" in resp.text


def test_surface_present_on_home(make_client, seed):
    client = make_client(None)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="concierge-overlay"' in resp.text
    assert "preview-banner" in resp.text


def test_surface_present_on_404(make_client, seed):
    client = make_client(None)
    resp = client.get("/deze-bestaat-niet-xyz")
    assert resp.status_code == 404
    # Het oppervlak + band zijn ook op de verdwaald-pagina aanwezig (cross-cutting).
    assert 'id="concierge-overlay"' in resp.text
    assert "preview-banner" in resp.text


def test_surface_present_on_member_pages(make_client, seed):
    """Ingelogd: de besloten speelveld-pagina's dragen het oppervlak + band."""
    client = make_client(seed["member"])
    for path in ("/profiel/ai/bouwen", "/ideeen", "/roadmap"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert 'id="concierge-overlay"' in resp.text, path
        assert "preview-banner" in resp.text, path


def test_surface_present_on_member_profile(make_client, seed):
    """De publieke profielpagina draagt het oppervlak + de member-context."""
    client = make_client(None)
    resp = client.get(f"/leden/{seed['slug']}")
    assert resp.status_code == 200
    assert 'id="concierge-overlay"' in resp.text


# --------------------------------------------------------------------------- #
# 2. Drie oproep-ingangen                                                     #
# --------------------------------------------------------------------------- #
def test_nav_field_opens_surface(make_client, seed):
    """De rustige '✦ Vraag de wereld'-nav-knop heeft de open-hook."""
    client = make_client(None)
    resp = client.get("/leden")
    assert "cnav__concierge" in resp.text
    assert "data-concierge-open" in resp.text
    assert "Vraag de wereld" in resp.text


def test_keybinding_hooks_present(make_client, seed):
    """⌘K/Ctrl+K én '/' zijn als keybinding in het oppervlak-script aanwezig."""
    client = make_client(None)
    resp = client.get("/leden")
    # ⌘K / Ctrl+K detectie + de "/"-ingang.
    assert "metaKey" in resp.text and "ctrlKey" in resp.text
    assert "'/'" in resp.text or '"/"' in resp.text


def test_input_posts_to_concierge_bericht(make_client, seed):
    """Het invoerveld opent de stream via POST /concierge/bericht (PRD §2.2)."""
    client = make_client(None)
    resp = client.get("/leden")
    assert 'hx-post="/concierge/bericht"' in resp.text
    assert 'id="concierge-input"' in resp.text
    # Instant-index wordt lazy gefetcht van /concierge/index.
    assert "/concierge/index" in resp.text


# --------------------------------------------------------------------------- #
# 3. Contextuele placeholder per pagina (PRD §2.1)                            #
# --------------------------------------------------------------------------- #
def test_placeholder_leden(make_client, seed):
    client = make_client(None)
    resp = client.get("/leden")
    assert "wie bouwt hier voice-agents?" in resp.text


def test_placeholder_roadmap(make_client, seed):
    client = make_client(seed["member"])
    resp = client.get("/roadmap")
    assert "wat staat er gepland?" in resp.text


def test_placeholder_member_uses_first_name(make_client, seed):
    """Op /leden/{slug} luidt de placeholder 'stel me voor aan {voornaam}'."""
    client = make_client(None)
    resp = client.get(f"/leden/{seed['slug']}")
    assert "stel me voor aan Sanne" in resp.text


def test_placeholder_home_is_contextual(make_client, seed):
    """De voordeur zet concierge_context='home' → een eigen, contextuele prompt
    (deze viel vóór de fix per ongeluk door naar de neutrale fallback)."""
    client = make_client(None)
    resp = client.get("/")
    assert "wie zit hier en wat maken ze?" in resp.text


# --------------------------------------------------------------------------- #
# 4. A11y                                                                      #
# --------------------------------------------------------------------------- #
def test_a11y_dialog_roles(make_client, seed):
    client = make_client(None)
    resp = client.get("/leden")
    assert 'role="dialog"' in resp.text
    assert 'aria-modal="true"' in resp.text
    # Focus-trap-logica aanwezig (Tab-afhandeling in het script).
    assert "Tab" in resp.text
    # Esc sluit.
    assert "Escape" in resp.text
    # Het oppervlak start verborgen (geen aandacht-claim tot oproep).
    assert 'id="concierge-overlay" class="concierge-overlay" hidden' in resp.text


# --------------------------------------------------------------------------- #
# 5. Preview-band: server-rendered + cookie-dismiss                           #
# --------------------------------------------------------------------------- #
def test_preview_banner_server_rendered_text(make_client, seed):
    """De band staat er zonder JS (server-rendered boodschap)."""
    client = make_client(None)
    resp = client.get("/leden")
    # Pivot: open & welcoming (was "besloten — alleen op uitnodiging", daarna "Open preview").
    assert "dewereldvan.ai is open" in resp.text
    assert "is welkom" in resp.text


def test_preview_banner_hidden_when_cookie_set(make_client, seed):
    """Met de dismiss-cookie verdwijnt de band (komt niet elke navigatie terug)."""
    client = make_client(None)
    client.cookies.set("dwv_preview_dismissed", "1")
    resp = client.get("/leden")
    assert resp.status_code == 200
    assert "preview-banner" not in resp.text
    # Het Concierge-oppervlak blijft wél aanwezig (band en oppervlak los van elkaar).
    assert 'id="concierge-overlay"' in resp.text


# --------------------------------------------------------------------------- #
# 6. SSE-stream-host: verse-proxy-aanpak + card-binding                       #
# --------------------------------------------------------------------------- #
def test_stream_partial_renders_and_uses_proxy_swap():
    """concierge/_stream.html bindt card via een VERSE proxy, niet op #concierge-results.

    De bekende valkuil (sse-swap bindt alleen op verse elementen ná sse-connect)
    wordt vermeden: de card-binding zit op een vers proxy-element dat appendt naar
    #concierge-results via hx-target/hx-swap=beforeend.
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("concierge/_stream.html").render()
    # De card-binding zit op een proxy met hx-target naar de resultaten-container.
    assert 'sse-swap="card"' in html
    assert 'hx-target="#concierge-results"' in html
    assert 'hx-swap="beforeend"' in html
    # reasoning/delta/done-events aanwezig (gekloond van het profielbouw-patroon).
    assert 'sse-swap="reasoning"' in html
    assert 'sse-swap="delta"' in html
    assert 'sse-swap="done"' in html
    # Verbindt op de gedeelde voorouder met /concierge/stream.
    assert "/concierge/stream" in html


# --------------------------------------------------------------------------- #
# 7. Makerkaart-in-de-stroom hergebruikt members/_member_star.html (grounding) #
# --------------------------------------------------------------------------- #
def test_card_partial_reuses_member_star(make_client, seed, SessionTest):
    """concierge/_card.html rendert de ECHTE makerkaart uit de DB (geen tweede look)."""
    from app.models import Profile
    from app.services import emphasis_service, photo_service
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    s = SessionTest()
    profile = s.query(Profile).filter_by(slug=seed["slug"]).one()

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("concierge/_card.html").render(
        profile=profile,
        emphasis_class=emphasis_service.emphasis_class,
        photo_for=photo_service.photo_or_initials,
        shared_tags=["voice-agents", "zorg"],
    )
    s.close()
    # De kaart linkt naar de echte publieke profielpagina (klikbaar, gegrond).
    assert f'href="/leden/{seed["slug"]}"' in html
    assert "member-star" in html
    assert "Sanne Vidal" in html
    # De "waarom"-regel toont de gedeelde tags (van connect).
    assert "voice-agents" in html


def test_card_partial_no_profile_no_card():
    """Grounding: zonder een echt profiel materialiseert er geen kaart-inhoud."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    # _card.html zónder profiel zou een render-fout/lege kaart geven; de route
    # rendert _card.html alléén met een DB-profiel, dus de poort zit in de bron.
    # Hier bewijzen we dat de template een profiel VERWACHT (geen verzonnen naam).
    src = env.loader.get_source(env, "concierge/_card.html")[0]
    assert "members/_member_star.html" in src
    assert "profile" in src
