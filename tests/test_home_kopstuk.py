"""Homepage-kopstuk (Blok 1, Concept B-hybride) — W1 + W2 op de voordeur.

Toetst dat de voordeur de belofte TOONT i.p.v. beweert:
- W2: de embedded demo (de agent bouwt een profiel vóór je ogen), gescript + fictief;
- W1: een echte mini-constellatie van leden met gegronde verbindingslijnen;
- de proef-chips gebruiken de VEILIGE prefill-haak (geen betaalde agent-call voor anon);
- /demo deelt de choreografie via /static/demo-play.js (geen duplicatie-drift).

Plus een unit-test op ``compute_graph_links`` (strict in-memory, nul AI).
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import itsdangerous
import pytest
from app.models import Member, MemberStatus, Profile, Tag, Visibility
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tests._route_helpers import make_route_engine

_SECRET = "test-secret-key-deterministic-0123456789abcdef"


def _session_cookie(data: dict) -> str:
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
    return sessionmaker(bind=route_engine, autoflush=False, future=True)


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


def _seed_public(SessionTest, n: int, *, shared_tag: str | None = None) -> None:
    """``n`` publieke, goedgekeurde profielen; optioneel allen met één gedeelde tag."""
    with SessionTest() as s:
        tag = None
        if shared_tag:
            tag = Tag(slug=shared_tag, name=shared_tag)
            s.add(tag)
            s.flush()
        for i in range(n):
            m = Member(
                email=f"maker{i}@example.com",
                name=f"Maker {i}",
                status=MemberStatus.approved,
            )
            s.add(m)
            s.flush()
            p = Profile(
                member_id=m.id,
                slug=f"maker-{i}",
                display_name=f"Maker {i}",
                visibility=Visibility.public,
                headline=f"Bouwt ding {i}",
            )
            if tag is not None:
                p.tags.append(tag)
            s.add(p)
        s.commit()


# --------------------------------------------------------------------------- #
# W2 — de embedded demo op de voordeur                                         #
# --------------------------------------------------------------------------- #
def test_home_anon_embeds_the_agent_demo(client):
    body = client.get("/").text
    # De gedeelde demo-root + autoplay + de gescripte choreografie-haken.
    assert 'data-demo' in body
    assert 'data-demo-autoplay' in body
    assert 'data-demo-type=' in body
    assert 'demo-step' in body
    # Verplicht eerlijk gelabeld als fictief (geen verzonnen echte mensen claimen).
    assert "fictief profiel" in body
    # Het gedeelde script is gelinkt (geen inline-duplicaat meer).
    assert "/static/demo-play.js" in body


def test_home_headline_promises_the_mechanism(client):
    body = client.get("/").text
    # De kop verkoopt het mechanisme (link → profiel), niet een holle claim.
    assert "Geef een link" in body


# --------------------------------------------------------------------------- #
# Proef-chips — veilig (geen betaalde agent-call voor anon)                    #
# --------------------------------------------------------------------------- #
def test_home_chips_use_safe_prefill_not_paid_submit(client):
    body = client.get("/").text
    assert "data-concierge-prefill=" in body
    # KILL-guard: de chips mogen NOOIT de auto-submittende fill-haak gebruiken
    # (die zou de betaalde, ongecapte agent-stream triggeren voor een anon).
    assert 'data-concierge-fill="wie bouwt' not in body
    assert 'data-concierge-fill="ik zoek' not in body


def test_home_promotes_proef_cta(client):
    body = client.get("/").text
    # Het echte intelligentie-bewijs staat prominent, niet begraven.
    assert "/proef" in body
    assert "Probeer het met je eigen link" in body


def test_home_demo_has_nojs_fallback(client):
    """Crawler/no-JS-vangnet: het W2-bewijs is óók zichtbaar zonder JS (de
    .demo-step/reasoning starten op opacity:0 en worden anders alleen door JS
    onthuld). De voordeur is de indexeerbare launch-pagina — het bewijs mag daar
    nooit stil verdwijnen."""
    body = client.get("/").text
    assert ".home-demo .demo-step" in body
    assert "opacity:1!important" in body


def test_anon_concierge_blocks_paid_agent_in_ui(client):
    """KILL-guard (kosten): een anonieme bezoeker mag de betaalde agent-stream
    nooit via de UI triggeren. De overlay rendert loggedIn=false → de afsluit-rij
    wordt 'word lid' (geen submit) en de htmx:confirm-poort cancelt elke submit."""
    body = client.get("/").text
    assert "var loggedIn = false;" in body
    # De anon-tak (word lid i.p.v. betaalde call) + de submit-poort staan in de bron.
    assert "Word lid om de agent dit te laten uitzoeken" in body
    assert "htmx:confirm" in body


def test_logged_in_concierge_enables_agent_flag(client, SessionTest):
    """Een ingelogd lid (hier: pending op de voordeur) krijgt loggedIn=true → de
    agent-ask-rij blijft beschikbaar."""
    with SessionTest() as s:
        m = Member(
            email="wacht@example.com", name="Wachtend", status=MemberStatus.pending
        )
        s.add(m)
        s.commit()
        mid = m.id
    client.cookies.set("session", _session_cookie({"member_id": mid}))
    body = client.get("/").text
    assert "var loggedIn = true;" in body


# --------------------------------------------------------------------------- #
# W1 — de echte makers-constellatie                                            #
# --------------------------------------------------------------------------- #
def test_home_constellation_shows_real_makers_at_three(client, SessionTest):
    _seed_public(SessionTest, 3)
    body = client.get("/").text
    assert "home-constellation" in body
    assert body.count("home-star ") + body.count('home-star"') >= 3 or "home-star" in body
    # Elke ster linkt naar een echt profiel + draagt een naam (geen anonieme bol).
    assert "/leden/maker-0" in body
    assert "Maker 0" in body


def test_home_constellation_draws_links_on_shared_tag(client, SessionTest):
    _seed_public(SessionTest, 3, shared_tag="voice-agents")
    body = client.get("/").text
    # Gedeelde tag → minstens één gegronde verbindingslijn in de SVG.
    assert "<line " in body


def test_home_constellation_hidden_below_three(client, SessionTest):
    _seed_public(SessionTest, 2)
    body = client.get("/").text
    assert "home-constellation" not in body
    # Eerlijke fallback i.p.v. nep-sterren.
    assert "De eerste makers" in body


# --------------------------------------------------------------------------- #
# /demo deelt de choreografie (geen drift)                                     #
# --------------------------------------------------------------------------- #
def test_demo_uses_shared_script(client):
    resp = client.get("/demo")
    assert resp.status_code == 200
    body = resp.text
    assert "/static/demo-play.js" in body
    assert 'data-demo' in body
    # De inline play-functie is weg (gedeeld via het bestand).
    assert "querySelectorAll('.demo-step')" not in body


def test_demo_shows_scan_to_field_causality(client):
    """W2-aanscherping: per veld een reasoning-regel ('homepage gelezen → naam'),
    zodat de bezoeker de scan→veld-causaliteit ziet i.p.v. een blinde timer."""
    body = client.get("/demo").text
    assert "data-demo-reasons" in body  # de uitvoer-container
    assert 'data-demo-reason=' in body  # ten minste één gekoppelde stap
    assert "homepage gelezen" in body


# --------------------------------------------------------------------------- #
# compute_graph_links — unit (strict in-memory, nul AI, nul query)            #
# --------------------------------------------------------------------------- #
def test_compute_graph_links_pairs_on_shared_tag_or_tool():
    from app.main import compute_graph_links

    def prof(tags=(), tools=()):
        return SimpleNamespace(
            tags=[SimpleNamespace(slug=t, name=t) for t in tags],
            tools=[SimpleNamespace(slug=t, name=t) for t in tools],
        )

    profiles = [
        prof(tags=["rag"]),            # 0
        prof(tags=["rag", "voice"]),   # 1 deelt rag met 0
        prof(tools=["langchain"]),     # 2 deelt niets
        prof(tools=["langchain"]),     # 3 deelt tool met 2
    ]
    links = compute_graph_links(profiles)
    assert [0, 1] in links
    assert [2, 3] in links
    assert [0, 2] not in links


def test_compute_graph_links_is_capped():
    from app.main import compute_graph_links

    # 8 profielen die ALLEMAAL dezelfde tag delen → 28 mogelijke paren, gecapt.
    shared = SimpleNamespace(
        tags=[SimpleNamespace(slug="x", name="x")], tools=[]
    )
    profiles = [shared for _ in range(8)]
    links = compute_graph_links(profiles, max_links=12)
    assert len(links) == 12
