"""Spam-triage bij registratie (pivot Fase B) — de poort filtert spam, niet mensen.

Twee niveaus:
- ``triage_service.assess_registration``: AI uit → review; WELKOM → welcome; al het
  andere (BEKIJK, onverwacht, fout) → review. Nooit auto-weren.
- HTTP ``POST /register``: welcome → auto-goedgekeurd (+ welkomst-mail), review →
  blijft pending (+ admin-notificatie). Triage gemonkeypatcht (geen netwerk).
"""

from __future__ import annotations

import re

import pytest
from app.config import settings
from app.models import Member, MemberStatus
from app.services import triage_service
from app.services.triage_service import TriageVerdict
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def client(engine, fake_email):
    """TestClient met DB + e-mail overschreven (zoals in test_app_smoke)."""
    from app.db import get_db
    from app.deps import email_sender as email_sender_dep
    from app.main import app

    SessionTest = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[email_sender_dep] = lambda: fake_email
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Mini fake-Anthropic die platte tekst teruggeeft (triage leest block.text)    #
# --------------------------------------------------------------------------- #
class _Block:
    def __init__(self, text: str) -> None:
        self.text = text


class _Resp:
    def __init__(self, text: str, stop_reason: str = "end_turn") -> None:
        self.content = [_Block(text)]
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, resp: _Resp | None, raise_exc: bool) -> None:
        self._resp = resp
        self._raise = raise_exc

    def create(self, **_kw):
        if self._raise:
            raise RuntimeError("boom")
        return self._resp


class _FakeClient:
    def __init__(self, resp: _Resp | None = None, raise_exc: bool = False) -> None:
        self.messages = _Messages(resp, raise_exc)


def _install(monkeypatch, *, text: str | None = None, stop_reason: str = "end_turn",
             raise_exc: bool = False) -> None:
    """Zet AI aan + vervang ``anthropic.Anthropic`` door een tekst-fake."""
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    import anthropic

    resp = None if text is None else _Resp(text, stop_reason)
    monkeypatch.setattr(
        anthropic, "Anthropic", lambda *a, **k: _FakeClient(resp, raise_exc)
    )


# --------------------------------------------------------------------------- #
# Service-niveau                                                              #
# --------------------------------------------------------------------------- #
def test_triage_disabled_returns_review(monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", False)
    v = triage_service.assess_registration("Iemand Echt", "iemand@example.com")
    assert v.decision == "review"
    assert not v.is_welcome


def test_triage_welcome_on_explicit_welkom(monkeypatch):
    _install(monkeypatch, text="WELKOM\nGewone naam, plausibel e-mailadres.")
    v = triage_service.assess_registration("Sanne de Boer", "sanne@example.com")
    assert v.is_welcome
    assert "plausibel" in v.reason


def test_triage_review_on_bekijk(monkeypatch):
    _install(monkeypatch, text="BEKIJK\nWartaal-naam, mogelijk een bot.")
    v = triage_service.assess_registration("xqz99zzz", "a8f3@spam.example")
    assert v.decision == "review"
    assert "bot" in v.reason


def test_triage_review_on_unexpected_output(monkeypatch):
    # Geen expliciete WELKOM → veilig terug naar review (nooit auto-welkom).
    _install(monkeypatch, text="misschien wel ok?")
    v = triage_service.assess_registration("Twijfel", "x@example.com")
    assert v.decision == "review"


def test_triage_review_on_refusal(monkeypatch):
    _install(monkeypatch, text="WELKOM\nirrelevant", stop_reason="refusal")
    v = triage_service.assess_registration("Iemand", "x@example.com")
    assert v.decision == "review"


def test_triage_review_on_error(monkeypatch):
    _install(monkeypatch, raise_exc=True)
    v = triage_service.assess_registration("Iemand", "x@example.com")
    assert v.decision == "review"  # fout → review, registratie strandt nooit


# --------------------------------------------------------------------------- #
# HTTP-laag — /register draait triage en handelt ernaar                       #
# --------------------------------------------------------------------------- #
def _csrf(client) -> str:
    page = client.get("/register")
    return re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)


def test_register_auto_welcomes_genuine(client, engine, monkeypatch):
    """WELKOM-verdict → lid wordt direct goedgekeurd + de pagina viert het."""
    from app.routers import auth

    monkeypatch.setattr(
        auth.triage_service, "assess_registration",
        lambda name, email: TriageVerdict("welcome", "Lijkt een echt mens"),
    )
    csrf = _csrf(client)
    resp = client.post(
        "/register",
        data={"name": "Echt Mens", "email": "echt@example.com", "csrf_token": csrf},
    )
    assert resp.status_code == 200
    assert "Je bent erbij" in resp.text  # auto-welkom-copy

    with Session(engine) as s:
        m = s.scalar(select(Member).where(Member.email == "echt@example.com"))
        assert m is not None
        assert m.status is MemberStatus.approved
        assert m.triage_note == "Lijkt een echt mens"


def test_register_notifies_admins_on_every_new_member(client, engine, monkeypatch):
    """Operator-wens: een admin-Telegram bij ELK nieuw lid — auto-welkom én review.

    Auto-verwelkomde leden slaan de queue over, dus zonder deze ping zou de operator
    die aanwas nergens zien. We vangen de notify-helper af en bewijzen dat hij in
    beide paden vuurt, met de juiste ``auto_welcomed``-vlag.
    """
    from app.routers import auth

    calls: list[bool] = []
    monkeypatch.setattr(
        auth, "_notify_admins_new_registration",
        lambda db, member, *, auto_welcomed: calls.append(auto_welcomed),
    )

    # 1) WELKOM → ping met auto_welcomed=True
    monkeypatch.setattr(
        auth.triage_service, "assess_registration",
        lambda name, email: TriageVerdict("welcome", "echt mens"),
    )
    r1 = client.post(
        "/register",
        data={"name": "Welkom Mens", "email": "welkom@example.com", "csrf_token": _csrf(client)},
    )
    assert r1.status_code == 200

    # 2) BEKIJK → ping met auto_welcomed=False
    monkeypatch.setattr(
        auth.triage_service, "assess_registration",
        lambda name, email: TriageVerdict("review", "twijfel"),
    )
    r2 = client.post(
        "/register",
        data={"name": "Review Mens", "email": "review@example.com", "csrf_token": _csrf(client)},
    )
    assert r2.status_code == 200

    assert calls == [True, False]

    # Een idempotente herhaling (zelfde e-mail, geen nieuw lid) seint NIET.
    client.post(
        "/register",
        data={"name": "Welkom Mens", "email": "welkom@example.com", "csrf_token": _csrf(client)},
    )
    assert calls == [True, False]  # ongewijzigd


def test_register_review_keeps_pending(client, engine, monkeypatch):
    """BEKIJK-verdict → lid blijft pending (mens beslist), met de reden in de queue."""
    from app.routers import auth

    monkeypatch.setattr(
        auth.triage_service, "assess_registration",
        lambda name, email: TriageVerdict("review", "Twijfel — handmatig bekeken"),
    )
    csrf = _csrf(client)
    resp = client.post(
        "/register",
        data={"name": "Twijfel", "email": "twijfel@example.com", "csrf_token": csrf},
    )
    assert resp.status_code == 200
    assert "we kijken even mee" in resp.text.lower() or "kijken alleen even mee" in resp.text

    with Session(engine) as s:
        m = s.scalar(select(Member).where(Member.email == "twijfel@example.com"))
        assert m is not None
        assert m.status is MemberStatus.pending
        assert m.triage_note == "Twijfel — handmatig bekeken"
