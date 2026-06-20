"""Tests voor de notificatie-laag — kanaalvoorkeur + Telegram-koppeling + dispatch.

Geen netwerk: ``telegram_service.send_message``/``configured`` worden gepatcht.
Service-tests draaien op de ``db``-fixture; route-tests (webhook + instellingen)
gebruiken een eigen in-memory engine + dependency-overrides (gespiegeld van de
discovery-route-tests).
"""

from __future__ import annotations

import pytest
from app.models import Base, MemberChannel, NotificationPref
from app.services import notification_service, telegram_service
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# --------------------------------------------------------------------------- #
# telegram_service.parse_start                                                 #
# --------------------------------------------------------------------------- #


def test_parse_start_reads_token_and_chat_id():
    update = {"message": {"text": "/start abc123", "chat": {"id": 4242}}}
    token, chat_id = telegram_service.parse_start(update)
    assert token == "abc123"
    assert chat_id == "4242"


def test_parse_start_non_start_has_no_token():
    update = {"message": {"text": "hoi", "chat": {"id": 7}}}
    token, chat_id = telegram_service.parse_start(update)
    assert token is None
    assert chat_id == "7"


def test_parse_start_garbage_is_safe():
    assert telegram_service.parse_start("nonsense") == (None, None)
    assert telegram_service.parse_start({}) == (None, None)


# --------------------------------------------------------------------------- #
# Voorkeur + koppeling (service)                                              #
# --------------------------------------------------------------------------- #


def test_preferred_channel_defaults_in_app(db, make_member, make_profile):
    member = make_member()
    make_profile(member)
    assert notification_service.preferred_channel(db, member) == "in_app"


def test_set_preference_telegram_without_link_falls_back(db, make_member, make_profile):
    member = make_member()
    make_profile(member)
    result = notification_service.set_preference(db, member, "telegram")
    assert result == "in_app"  # niet gekoppeld → terug naar in-app
    assert notification_service.preferred_channel(db, member) == "in_app"


def test_link_flow_then_prefer_telegram(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(telegram_service, "configured", lambda: True)
    monkeypatch.setattr(telegram_service, "link_url", lambda tok: f"https://t.me/bot?start={tok}")
    member = make_member()
    make_profile(member)

    link = notification_service.begin_telegram_link(db, member)
    assert link and link.startswith("https://t.me/bot?start=")
    assert notification_service.telegram_status(db, member) == "pending"

    # Simuleer de webhook: koppel een chat_id op het uitgegeven token.
    ch = db.query(MemberChannel).filter_by(member_id=member.id).one()
    assert notification_service.link_telegram_from_start(db, ch.link_token, "999")
    assert notification_service.telegram_status(db, member) == "linked"

    # Nu mag telegram als voorkeur gezet worden.
    assert notification_service.set_preference(db, member, "telegram") == "telegram"


def test_begin_link_returns_none_when_not_configured(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(telegram_service, "configured", lambda: False)
    member = make_member()
    make_profile(member)
    assert notification_service.begin_telegram_link(db, member) is None


def test_unlink_resets_preference(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(telegram_service, "configured", lambda: True)
    monkeypatch.setattr(telegram_service, "link_url", lambda tok: f"https://t.me/b?start={tok}")
    member = make_member()
    make_profile(member)
    notification_service.begin_telegram_link(db, member)
    ch = db.query(MemberChannel).filter_by(member_id=member.id).one()
    notification_service.link_telegram_from_start(db, ch.link_token, "5")
    notification_service.set_preference(db, member, "telegram")

    notification_service.unlink_telegram(db, member)
    assert notification_service.telegram_status(db, member) == "none"
    assert notification_service.preferred_channel(db, member) == "in_app"


# --------------------------------------------------------------------------- #
# Dispatch (notify) — gating op het voorkeurskanaal                           #
# --------------------------------------------------------------------------- #


def test_notify_in_app_does_not_push(db, make_member, make_profile, monkeypatch):
    sent: list = []
    monkeypatch.setattr(telegram_service, "send_message", lambda cid, txt: sent.append((cid, txt)))
    member = make_member()
    make_profile(member)
    notification_service.notify(
        db, member, notification_service.Notification("x", "Titel", "Body", url="/p")
    )
    assert sent == []  # default in-app → geen push


def test_notify_telegram_pushes(db, make_member, make_profile, monkeypatch):
    sent: list = []
    monkeypatch.setattr(telegram_service, "configured", lambda: True)
    monkeypatch.setattr(telegram_service, "link_url", lambda tok: f"https://t.me/b?start={tok}")
    monkeypatch.setattr(telegram_service, "send_message", lambda cid, txt: sent.append((cid, txt)))
    member = make_member()
    make_profile(member)
    notification_service.begin_telegram_link(db, member)
    ch = db.query(MemberChannel).filter_by(member_id=member.id).one()
    notification_service.link_telegram_from_start(db, ch.link_token, "777")
    notification_service.set_preference(db, member, "telegram")

    notification_service.notify(
        db, member, notification_service.Notification(
            "discovery_ready", "Klaar", "2 vermeldingen", url="/profiel/ai/ontdek/resultaat"
        )
    )
    assert len(sent) == 1
    assert sent[0][0] == "777"
    assert "Klaar" in sent[0][1] and "resultaat" in sent[0][1]


# --------------------------------------------------------------------------- #
# Routes: webhook + instellingen                                             #
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
    return sessionmaker(bind=route_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def approved_id(SessionTest):
    from app.models import Member, MemberStatus

    s = SessionTest()
    m = Member(email="notif@example.com", name="Notif Lid", status=MemberStatus.approved)
    s.add(m)
    s.commit()
    mid = m.id
    s.close()
    return mid


@pytest.fixture
def make_client(route_engine, SessionTest):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app
    from app.models import Member
    from fastapi import Depends
    from sqlalchemy.orm import Session

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
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def _csrf(client) -> str:
    import re

    page = client.get("/profiel/notificaties")
    assert page.status_code == 200
    # De pagina draagt de CSRF-token via hx-headers op <body> (letterlijke quotes).
    m = re.search(r'X-CSRF-Token"\s*:\s*"([^"]+)"', page.text)
    assert m, "CSRF token not found"
    return m.group(1)


def test_settings_page_renders(make_client, approved_id):
    client = make_client(approved_id)
    resp = client.get("/profiel/notificaties")
    assert resp.status_code == 200
    assert "Waar wil je een seintje" in resp.text
    assert "notif-panel" in resp.text


def test_settings_page_anonymous_blocked(make_client):
    client = make_client(None)
    resp = client.get("/profiel/notificaties", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_set_channel_persists(make_client, approved_id, SessionTest):
    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/notificaties/kanaal",
        data={"channel": "telegram"},  # niet gekoppeld → valt terug op in_app
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    with SessionTest() as s:
        pref = s.get(NotificationPref, approved_id)
        assert pref.channel == "in_app"


def test_webhook_rejects_bad_secret(make_client, approved_id, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_webhook_secret", "geheim")
    client = make_client(approved_id)
    resp = client.post(
        "/telegram/webhook",
        json={"message": {"text": "/start x", "chat": {"id": 1}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "fout"},
    )
    assert resp.status_code == 403


def test_webhook_links_chat_id(make_client, approved_id, SessionTest, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_webhook_secret", "geheim")
    monkeypatch.setattr(telegram_service, "send_message", lambda cid, txt: None)

    # Zet een pending channel met een bekend token.
    with SessionTest() as s:
        s.add(MemberChannel(member_id=approved_id, channel="telegram", link_token="tok-1"))
        s.commit()

    client = make_client(approved_id)
    resp = client.post(
        "/telegram/webhook",
        json={"message": {"text": "/start tok-1", "chat": {"id": 31337}}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "geheim"},
    )
    assert resp.status_code == 200
    with SessionTest() as s:
        ch = s.query(MemberChannel).filter_by(member_id=approved_id).one()
        assert ch.address == "31337"
        assert ch.verified_at is not None
        assert ch.link_token is None
