"""Tests voor connect/intro (Tier 1 Fase 2): persisteren + notificatie + accept/
decline + consent-poort + chip + surface + AVG.

E-mail via een ``FakeEmailSender`` (geen netwerk). Wegwerp-engine per test.
"""

from __future__ import annotations

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests._route_helpers import csrf_token, make_route_engine


@pytest.fixture
def route_engine():
    eng = make_route_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(bind=route_engine, autoflush=False, autocommit=False, future=True)


def _setup(s):
    """Zoeker A + maker B + een match-suggestie (A zoekt, B biedt)."""
    from app.models import Member, MemberStatus, Need, Offering, Profile, Visibility
    from app.models.match_suggestion import MatchSuggestion

    a = Member(email="a@x.nl", name="Alice", status=MemberStatus.approved)
    b = Member(email="b@x.nl", name="Bob", status=MemberStatus.approved)
    s.add_all([a, b])
    s.flush()
    pa = Profile(member_id=a.id, slug="alice", display_name="Alice",
                 visibility=Visibility.members, completeness=50)
    pb = Profile(member_id=b.id, slug="bob", display_name="Bob",
                 visibility=Visibility.members, completeness=50)
    s.add_all([pa, pb])
    s.flush()
    need = Need(profile_id=pa.id, title="Hulp met voice agents")
    off = Offering(profile_id=pb.id, title="Voice agent platform")
    s.add_all([need, off])
    s.flush()
    ms = MatchSuggestion(
        need_id=need.id, offering_id=off.id, seeker_member_id=a.id,
        maker_member_id=b.id, score=80, rationale="past goed",
    )
    s.add(ms)
    s.commit()
    return {"a": a.id, "b": b.id, "match": ms.id}


@pytest.fixture
def seed(SessionTest):
    s = SessionTest()
    ids = _setup(s)
    s.close()
    return ids


class FakeSender:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


@pytest.fixture
def make_client(route_engine, SessionTest):
    from app.db import get_db
    from app.deps import current_member, email_sender
    from app.main import app
    from app.models import Member

    sender = FakeSender()

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    def _factory(member_id):
        def _override_current_member(db: Session = Depends(get_db)):
            return db.get(Member, member_id) if member_id is not None else None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        app.dependency_overrides[email_sender] = lambda: sender
        return TestClient(app, base_url="https://testserver")

    yield _factory, sender
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Service: counterpart + create + idempotent                                  #
# --------------------------------------------------------------------------- #
def test_counterpart_and_create_sets_acted(SessionTest, seed):
    from app.models import MatchStatus, Member
    from app.models.match_suggestion import MatchSuggestion
    from app.services import connection_service

    s = SessionTest()
    ms = s.get(MatchSuggestion, seed["match"])
    alice = s.get(Member, seed["a"])
    bob = s.get(Member, seed["b"])
    assert connection_service.counterpart_for_match(ms, alice) == seed["b"]
    assert connection_service.counterpart_for_match(ms, bob) == seed["a"]

    conn = connection_service.create_intro(s, from_member=alice, to_member=bob,
                                           message="Hoi!", match=ms)
    s.commit()
    assert conn.from_member_id == seed["a"]
    assert conn.to_member_id == seed["b"]
    assert s.get(MatchSuggestion, seed["match"]).status == MatchStatus.acted

    # idempotent: tweede keer geen duplicaat
    again = connection_service.create_intro(s, from_member=alice, to_member=bob,
                                            message="nogmaals", match=ms)
    s.commit()
    assert again.id == conn.id
    s.close()


# --------------------------------------------------------------------------- #
# Route: intro starten + notificatie                                          #
# --------------------------------------------------------------------------- #
def test_post_intro_creates_connection_and_notifies(make_client, seed, SessionTest, monkeypatch):
    from app.models.connection import Connection
    from app.services import notification_service

    notified: list = []
    monkeypatch.setattr(
        notification_service, "notify",
        lambda db, member, notif: notified.append((member.id, notif.kind)),
    )

    factory, sender = make_client
    client = factory(seed["a"])  # Alice stelt zich voor aan Bob
    token = csrf_token(client, "/leden")  # haal een geldig CSRF-token
    resp = client.post(
        "/intro",
        data={"match_id": seed["match"], "message": "Zullen we kennismaken?"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "Verstuurd" in resp.text or "Bob" in resp.text

    s = SessionTest()
    rows = s.query(Connection).all()
    assert len(rows) == 1
    assert rows[0].from_member_id == seed["a"]
    assert rows[0].to_member_id == seed["b"]
    s.close()

    # Geen e-mail meer; wél een seintje naar de ontvanger via diens voorkeurskanaal.
    assert sender.sent == []
    assert notified == [(seed["b"], "intro_received")]


def test_intro_form_prefilled(make_client, seed):
    factory, _ = make_client
    client = factory(seed["a"])
    resp = client.get(f"/intro/nieuw?match={seed['match']}")
    assert resp.status_code == 200
    assert "Bob" in resp.text  # de tegenpartij
    assert 'hx-post="/intro"' in resp.text


# --------------------------------------------------------------------------- #
# Route: accept/decline + consent-poort                                       #
# --------------------------------------------------------------------------- #
def _make_intro(SessionTest, seed):
    from app.models import Member
    from app.models.match_suggestion import MatchSuggestion
    from app.services import connection_service

    s = SessionTest()
    ms = s.get(MatchSuggestion, seed["match"])
    a = s.get(Member, seed["a"])
    b = s.get(Member, seed["b"])
    conn = connection_service.create_intro(s, from_member=a, to_member=b, message="Hoi Bob", match=ms)
    s.commit()
    cid = conn.id
    s.close()
    return cid


def test_accept_reveals_contact_only_for_recipient(make_client, seed, SessionTest):
    from app.models import ConnectionStatus
    from app.models.connection import Connection

    cid = _make_intro(SessionTest, seed)
    factory, _ = make_client

    # Alice (afzender) mag NIET accepteren
    alice = factory(seed["a"])
    token = csrf_token(alice, "/leden")
    r = alice.post(f"/intro/{cid}/accept", headers={"X-CSRF-Token": token},
                   follow_redirects=False)
    assert r.status_code in (302, 303, 403)

    # Bob (ontvanger) accepteert → contact (e-mail) zichtbaar in de kaart
    bob = factory(seed["b"])
    token = csrf_token(bob, "/leden")
    r = bob.post(f"/intro/{cid}/accept", headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    assert "a@x.nl" in r.text  # Alice' contact ontsloten ná akkoord

    s = SessionTest()
    assert s.get(Connection, cid).status == ConnectionStatus.accepted
    s.close()


def test_decline_sets_status(make_client, seed, SessionTest):
    from app.models import ConnectionStatus
    from app.models.connection import Connection

    cid = _make_intro(SessionTest, seed)
    factory, _ = make_client
    bob = factory(seed["b"])
    token = csrf_token(bob, "/leden")
    r = bob.post(f"/intro/{cid}/decline", headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    s = SessionTest()
    assert s.get(Connection, cid).status == ConnectionStatus.declined
    s.close()


# --------------------------------------------------------------------------- #
# Chip + surface + registry                                                   #
# --------------------------------------------------------------------------- #
def test_pending_intro_chip(SessionTest, seed):
    from app.models import Member
    from app.services import nudge_service

    _make_intro(SessionTest, seed)
    s = SessionTest()
    bob = s.get(Member, seed["b"])  # ontvanger heeft een pending intro
    chips = nudge_service.select_chips(s, bob)
    assert any(c.kind == "chip_intros" for c in chips)
    s.close()


def test_connections_surface_loader_and_registry(SessionTest, seed):
    from app.routers import concierge as cr
    from app.services import concierge_service

    _make_intro(SessionTest, seed)
    s = SessionTest()
    tmpl, ctx = cr._load_connections(s, {}, seed["b"], False)
    assert tmpl == "connections/_list.html"
    assert len(ctx["connections"]) == 1
    s.close()

    assert "connections" in concierge_service.SURFACE_REGISTRY
    surf = next(t for t in concierge_service.TOOLS if t["name"] == "surface")
    assert "connections" in set(surf["input_schema"]["properties"]["view"]["enum"])


# --------------------------------------------------------------------------- #
# AVG: accountverwijdering ruimt intro's op                                   #
# --------------------------------------------------------------------------- #
def test_account_deletion_removes_connections(SessionTest, seed):
    from app.models import Member
    from app.models.connection import Connection
    from app.services.account_deletion import delete_member_completely

    cid = _make_intro(SessionTest, seed)
    s = SessionTest()
    assert s.get(Connection, cid) is not None
    delete_member_completely(s, s.get(Member, seed["b"]))  # ontvanger weg
    s.commit()
    assert s.query(Connection).count() == 0
    s.close()
