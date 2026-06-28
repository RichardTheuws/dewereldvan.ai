"""Route-smoke voor de publieke voordeur (Concept A — /proef).

Geen netwerk, geen Anthropic-key, geen Cloudflare:
- ``get_db`` wijst naar een wegwerp in-memory engine (committe rijen blijven
  hermetisch binnen de test, net als ``test_ai_profile_routes``).
- De DURE call wordt op de service-grens gemockt: ``visitor_url_card.build_card``
  (zo raken we nooit Browser Rendering of de Anthropic-SDK).
- ``turnstile_service.configured`` / ``verify`` worden gemonkeypatcht.

Dekt: GET zonder/met Turnstile-keys, POST allowed (1 spend-rij), POST cache-hit
(geen nieuwe rij), degradatie-staten (weekcap/daglimiet/turnstile) zonder spend,
en URL-validatie.
"""

from __future__ import annotations

import re

import pytest
from app.models import AiSpendLog, Base
from app.services.visitor_url_card import CardResult
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
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
def client(route_engine, SessionTest):
    from app.db import get_db
    from app.main import app

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app, base_url="https://testserver")
    app.dependency_overrides.clear()


@pytest.fixture
def turnstile_on(monkeypatch):
    """Turnstile geconfigureerd + token altijd geldig (gate-stap 1 slaagt)."""
    from app.config import settings
    from app.services import turnstile_service

    monkeypatch.setattr(settings, "turnstile_site_key", "1x-site")
    monkeypatch.setattr(settings, "turnstile_secret_key", "1x-secret")
    monkeypatch.setattr(turnstile_service, "configured", lambda: True)
    monkeypatch.setattr(turnstile_service, "verify", lambda token, ip=None: True)


def _csrf(client: TestClient) -> str:
    page = client.get("/proef")
    assert page.status_code == 200
    m = re.search(r'X-CSRF-Token": "([^"]+)"', page.text)
    assert m, "CSRF token niet gevonden op /proef"
    return m.group(1)


def _mock_card(monkeypatch, *, text="WIE: Een maker.\nTHEMA: ai, zorg\nMATCH: bij zorgtech-makers"):
    """Mock de dure call: geef een vaste kaart + tokens terug, geen netwerk."""
    from app.services import visitor_url_card

    def _fake(url, **kw):
        return CardResult(text=text, input_tokens=12000, output_tokens=600)

    monkeypatch.setattr(visitor_url_card, "build_card", _fake)


def _spend_rows(SessionTest) -> int:
    s = SessionTest()
    try:
        return s.scalar(select(func.count()).select_from(AiSpendLog)) or 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# GET /proef                                                                   #
# --------------------------------------------------------------------------- #
def test_get_without_turnstile_keys_shows_safe_default(client, monkeypatch):
    from app.config import settings
    from app.services import turnstile_service

    monkeypatch.setattr(settings, "turnstile_site_key", None)
    monkeypatch.setattr(turnstile_service, "configured", lambda: False)
    resp = client.get("/proef")
    assert resp.status_code == 200
    # Veilige default: geen input, wel de word-lid-CTA.
    assert 'name="url"' not in resp.text
    assert "cf-turnstile" not in resp.text
    assert "Binnenkort" in resp.text


def test_get_with_turnstile_keys_shows_input_and_widget(client, turnstile_on):
    resp = client.get("/proef")
    assert resp.status_code == 200
    assert 'name="url"' in resp.text
    assert "cf-turnstile" in resp.text
    assert 'data-sitekey="1x-site"' in resp.text


def test_get_shows_agent_reading_state(client, turnstile_on):
    """De 'agent leest …'-staat is aanwezig + via hx-indicator gekoppeld, zodat de
    bezoeker de agent ZIET werken tijdens de call (geen dode spinner)."""
    resp = client.get("/proef")
    assert resp.status_code == 200
    assert 'id="proef-reading"' in resp.text
    assert 'hx-indicator="#proef-reading"' in resp.text
    assert "de agent leest" in resp.text


# --------------------------------------------------------------------------- #
# POST /proef — allowed → mini-kaart + één spend-rij                           #
# --------------------------------------------------------------------------- #
def test_post_allowed_renders_card_and_books_one_spend_row(
    client, turnstile_on, monkeypatch, SessionTest
):
    _mock_card(monkeypatch)
    token = _csrf(client)
    resp = client.post(
        "/proef",
        data={"url": "https://voorbeeld.nl/", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    # De mini-kaart is gerenderd (3 delen + toegang-CTA).
    assert "Wat onze agent ziet" in resp.text
    assert "Een maker." in resp.text
    assert "Vraag toegang" in resp.text

    # Precies één geboekte rij met de gemockte tokens.
    s = SessionTest()
    try:
        rows = s.scalars(select(AiSpendLog)).all()
        assert len(rows) == 1
        assert rows[0].input_tokens == 12000
        assert rows[0].output_tokens == 600
        assert rows[0].concept == "url_card"
        assert rows[0].cost_eur_micros > 0
    finally:
        s.close()


def test_post_response_headers_valid_and_visitor_cookie_carried(
    client, turnstile_on, monkeypatch
):
    """Regressie: ``_fragment`` mocht NIET alle ``response.raw_headers`` mee-extenden.

    De lege ``HTMLResponse`` draagt z'n eigen ``content-length: 0`` mee; die erbij
    plakken gaf een tweede, conflicterende Content-Length → een malformed respons
    die Cloudflare met **502** weigerde (origin logde 200) → /proef "deed niks".
    De fix neemt alleen de ``set-cookie`` (visitor-cookie) over. Borg: precies één
    Content-Length, en de visitor-cookie wordt nog steeds gezet.
    """
    from app.security import VISITOR_COOKIE

    _mock_card(monkeypatch)
    token = _csrf(client)
    resp = client.post(
        "/proef",
        data={"url": "https://voorbeeld.nl/", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    # Geen dubbele Content-Length (de 502-oorzaak).
    assert len(resp.headers.get_list("content-length")) == 1
    # De visitor-cookie (daglimiet-telunit) wordt nog steeds gezet.
    assert VISITOR_COOKIE in resp.cookies
    # En de kaart-inhoud is gewoon aanwezig.
    assert "Wat onze agent ziet" in resp.text


def test_post_card_shows_source_attribution(client, turnstile_on, monkeypatch):
    """Gegrondheid zichtbaar: de verse kaart toont 'gelezen van <host>' — het
    anti-hallucinatie-signaal dat de noordster eist."""
    _mock_card(monkeypatch)
    token = _csrf(client)
    resp = client.post(
        "/proef",
        data={"url": "https://voorbeeld.nl/over", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "gelezen van voorbeeld.nl" in resp.text


def test_post_empty_card_shows_honest_empty_state(client, turnstile_on, monkeypatch):
    """Refusal/te dunne pagina (lege kaarttekst) → eerlijke lege-staat i.p.v. een
    kale kaart met alleen een CTA."""
    _mock_card(monkeypatch, text="")
    token = _csrf(client)
    resp = client.post(
        "/proef",
        data={"url": "https://leeg.nl", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "weinig uit halen" in resp.text


# --------------------------------------------------------------------------- #
# POST /proef — cache-hit → geen nieuwe rij, kaart uit cache                   #
# --------------------------------------------------------------------------- #
def test_post_cache_hit_serves_from_cache_no_new_row(
    client, turnstile_on, monkeypatch, SessionTest
):
    # Eerste call boekt een rij; anti-burst zou een tweede meteen blokkeren, dus
    # zet die op 0 zodat we de CACHE-tak isoleren (identieke URL binnen TTL).
    from app.config import settings

    monkeypatch.setattr(settings, "visitor_ai_min_seconds_between_calls", 0)
    _mock_card(monkeypatch, text="WIE: Uniek.\nTHEMA: x\nMATCH: y")

    token = _csrf(client)
    first = client.post(
        "/proef",
        data={"url": "https://herhaald.nl", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert first.status_code == 200
    assert _spend_rows(SessionTest) == 1

    # Tweede identieke URL → cache-hit. De build_card-mock mag NIET nog eens draaien;
    # laat 'm crashen zodat een onbedoelde call de test breekt.
    from app.services import visitor_url_card

    def _boom(url, **kw):
        raise AssertionError("cache-hit mag geen nieuwe call doen")

    monkeypatch.setattr(visitor_url_card, "build_card", _boom)

    second = client.post(
        "/proef",
        data={"url": "https://herhaald.nl", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert second.status_code == 200
    assert "Uniek." in second.text  # zelfde kaart uit de cache
    assert _spend_rows(SessionTest) == 1  # GEEN nieuwe rij


# --------------------------------------------------------------------------- #
# POST /proef — degradatie-staten zonder spend                                 #
# --------------------------------------------------------------------------- #
def test_post_turnstile_fail_degrades_no_spend(
    client, turnstile_on, monkeypatch, SessionTest
):
    from app.services import turnstile_service

    monkeypatch.setattr(turnstile_service, "verify", lambda token, ip=None: False)
    _mock_card(monkeypatch)
    token = _csrf(client)
    resp = client.post(
        "/proef",
        data={"url": "https://voorbeeld.nl", "cf-turnstile-response": "bad"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "verifieren" in resp.text
    assert _spend_rows(SessionTest) == 0


def test_post_weekcap_degrades_no_spend(
    client, turnstile_on, monkeypatch, SessionTest
):
    from app.config import settings

    # Weekcap op 0 → elke voorschat overschrijdt → gate weigert vóór de call.
    monkeypatch.setattr(settings, "visitor_ai_budget_eur_per_week", 0.0)
    _mock_card(monkeypatch)
    token = _csrf(client)
    resp = client.post(
        "/proef",
        data={"url": "https://voorbeeld.nl", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "deze week op" in resp.text
    assert _spend_rows(SessionTest) == 0


def test_post_day_visitor_limit_degrades_no_spend(
    client, turnstile_on, monkeypatch, SessionTest
):
    from app.config import settings

    monkeypatch.setattr(settings, "visitor_ai_calls_per_day", 1)
    monkeypatch.setattr(settings, "visitor_ai_min_seconds_between_calls", 0)
    _mock_card(monkeypatch, text="WIE: A.\nTHEMA: b\nMATCH: c")
    token = _csrf(client)

    # Eerste call slaagt (daglimiet = 1), boekt een rij.
    first = client.post(
        "/proef",
        data={"url": "https://een.nl", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert first.status_code == 200
    assert _spend_rows(SessionTest) == 1

    # Tweede (andere URL → geen cache) raakt de daglimiet → degradatie, geen rij.
    second = client.post(
        "/proef",
        data={"url": "https://twee.nl", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert second.status_code == 200
    assert "vandaag de gratis proef" in second.text
    assert _spend_rows(SessionTest) == 1  # geen tweede boeking


# --------------------------------------------------------------------------- #
# POST /proef — URL-validatie                                                  #
# --------------------------------------------------------------------------- #
def test_post_invalid_url_no_call_no_spend(
    client, turnstile_on, monkeypatch, SessionTest
):
    _mock_card(monkeypatch)
    token = _csrf(client)
    resp = client.post(
        "/proef",
        data={"url": "ftp://nietgeldig", "cf-turnstile-response": "tok"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "geen geldige link" in resp.text
    assert _spend_rows(SessionTest) == 0
