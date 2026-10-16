"""Aanvragen van bezoekers (PRD hub §4.1) — service + routes.

Hermetisch: in-memory SQLite, Turnstile gemonkeypatcht, ``notify`` vervangen door
een recorder (geen Telegram). Dekt de edge cases uit PRD-hub §6: besloten profiel,
honeypot/te snel, validatie, rate-limits, dedupe, inbox-eigendom, spam, wissen,
bewaartermijn, en dat er nooit betaalde AI aan te pas komt.
"""

from __future__ import annotations

import re
import time
from datetime import timedelta

import pytest
from app.models import (
    AiSpendLog,
    Base,
    Inquiry,
    InquiryStatus,
    Member,
    MemberStatus,
    Profile,
    Visibility,
)
from app.security import naive_utc, utcnow
from app.services import account_deletion, inquiry_service, nudge_service
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

GOOD = dict(
    name="Sanne de Vries",
    email="Sanne@Bureau.nl",
    org="Bureau Noord",
    topic="trainingen",
    message="Wij zoeken een trainer voor een AI-sessie met ons team in november.",
    consent=True,
)


@pytest.fixture
def notified(monkeypatch):
    sent: list = []
    from app.services import notification_service

    monkeypatch.setattr(
        notification_service, "notify", lambda db, member, n: sent.append((member.id, n))
    )
    return sent


@pytest.fixture
def maker(db, make_member, make_profile):
    member = make_member(email="maker@example.com", name="Mila Maker")
    profile = make_profile(member, display_name="Mila Maker", visibility=Visibility.public)
    profile.open_to = ["klantwerk", "trainingen"]
    db.flush()
    return profile


# --------------------------------------------------------------------------- #
# Service                                                                      #
# --------------------------------------------------------------------------- #
def test_submit_stores_and_notifies(db, maker, notified):
    res = inquiry_service.submit(db, maker, ip="1.2.3.4", **GOOD)
    assert res.status == "ok" and res.created
    iq = res.inquiry
    assert iq.sender_email == "sanne@bureau.nl"
    assert iq.status == InquiryStatus.new
    assert iq.ip_hash != "1.2.3.4" and len(iq.ip_hash) == 64  # nooit het ruwe IP
    assert len(notified) == 1
    member_id, n = notified[0]
    assert member_id == maker.member_id
    assert n.kind == "inquiry_received" and "Sanne de Vries" in n.title
    assert n.url == f"/aanvragen/{iq.id}"


def test_members_only_profile_is_closed(db, maker, notified):
    maker.visibility = Visibility.members
    db.flush()
    assert inquiry_service.submit(db, maker, ip="1.2.3.4", **GOOD).status == "closed"
    assert not notified


def test_suspended_owner_is_closed(db, maker):
    db.get(Member, maker.member_id).status = MemberStatus.suspended
    db.flush()
    assert not inquiry_service.accepts_inquiries(maker)


def test_honeypot_and_speed_are_silent(db, maker, notified):
    assert inquiry_service.submit(db, maker, ip="1", honeypot="spam.biz", **GOOD).status == "silent"
    now = utcnow()
    res = inquiry_service.submit(
        db, maker, ip="1", started_at=naive_utc(now).timestamp() - 1, now=now, **GOOD
    )
    assert res.status == "silent"
    assert db.scalar(select(func.count(Inquiry.id))) == 0
    assert not notified


@pytest.mark.parametrize(
    "override,field",
    [
        ({"name": "x"}, "name"),
        ({"email": "geen-mail"}, "email"),
        ({"topic": "spreken"}, "topic"),  # niet in open_to van dit lid
        ({"message": "te kort"}, "message"),
        ({"message": "x" * 2001}, "message"),
        ({"consent": False}, "consent"),
    ],
)
def test_validation(db, maker, override, field):
    res = inquiry_service.submit(db, maker, ip="1", **{**GOOD, **override})
    assert res.status == "invalid" and field in res.errors


def test_topic_other_always_allowed(db, maker, notified):
    assert inquiry_service.submit(db, maker, ip="1", **{**GOOD, "topic": "anders"}).status == "ok"


def test_hidden_open_to_section_only_offers_other(db, maker):
    maker.public_sections = ["bio", "makes", "needs"]
    db.flush()
    assert [slug for slug, _ in inquiry_service.topics_for(maker)] == ["anders"]


def test_dedupe_is_idempotent(db, maker, notified):
    first = inquiry_service.submit(db, maker, ip="1", **GOOD)
    again = inquiry_service.submit(
        db, maker, ip="1", **{**GOOD, "message": "  " + GOOD["message"].upper()}
    )
    assert again.status == "ok" and not again.created and again.inquiry.id == first.inquiry.id
    assert len(notified) == 1


def test_ip_limit(db, maker, notified):
    for i in range(inquiry_service.IP_LIMIT_24H):
        assert (
            inquiry_service.submit(
                db, maker, ip="9", **{**GOOD, "message": GOOD["message"] + f" {i}"}
            ).status
            == "ok"
        )
    res = inquiry_service.submit(
        db, maker, ip="9", **{**GOOD, "message": GOOD["message"] + " extra"}
    )
    assert res.status == "limit"
    # Een ander IP mag nog wel.
    assert (
        inquiry_service.submit(
            db, maker, ip="10", **{**GOOD, "message": GOOD["message"] + " ander"}
        ).status
        == "ok"
    )


def test_inbox_ownership_and_status(db, maker, make_member, notified):
    iq = inquiry_service.submit(db, maker, ip="1", **GOOD).inquiry
    owner = db.get(Member, maker.member_id)
    stranger = make_member(email="ander@example.com")
    assert inquiry_service.get_for_member(db, stranger, iq.id) is None
    assert inquiry_service.count_new(db, owner) == 1
    inquiry_service.mark_read(db, iq)
    assert iq.status == InquiryStatus.read and iq.read_at is not None
    inquiry_service.set_status(db, iq, InquiryStatus.spam)
    assert inquiry_service.list_for_member(db, owner) == []
    assert inquiry_service.count_new(db, owner) == 0


def test_chip_shows_new_inquiries(db, maker, notified):
    inquiry_service.submit(db, maker, ip="1", **GOOD)
    owner = db.get(Member, maker.member_id)
    chips = nudge_service.select_chips(db, owner)
    chip = next(c for c in chips if c.kind == "chip_inquiries")
    assert chip.message.startswith("1 nieuwe vraag") and chip.action == "navigate:/aanvragen"


def test_purge_after_retention(db, maker, notified):
    iq = inquiry_service.submit(db, maker, ip="1", **GOOD).inquiry
    later = utcnow() + timedelta(days=inquiry_service.RETENTION_DAYS + 1)
    assert inquiry_service.purge_expired(db, now=later) == 1
    assert db.get(Inquiry, iq.id) is None


def test_account_deletion_removes_inquiries(db, maker, notified):
    inquiry_service.submit(db, maker, ip="1", **GOOD)
    account_deletion.delete_member_completely(db, db.get(Member, maker.member_id))
    assert db.scalar(select(func.count(Inquiry.id))) == 0


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@pytest.fixture
def route_db():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, autoflush=False, future=True)
    with Session() as s:
        m = Member(email="maker@example.com", name="Mila Maker", status=MemberStatus.approved)
        s.add(m)
        s.flush()
        s.add(
            Profile(
                member_id=m.id,
                slug="mila",
                display_name="Mila Maker",
                visibility=Visibility.public,
                open_to=["trainingen"],
            )
        )
        m2 = Member(email="besloten@example.com", name="Bo Besloten", status=MemberStatus.approved)
        s.add(m2)
        s.flush()
        s.add(
            Profile(
                member_id=m2.id,
                slug="bo",
                display_name="Bo Besloten",
                visibility=Visibility.members,
            )
        )
        s.commit()
    yield Session
    eng.dispose()


@pytest.fixture
def client(route_db, notified):
    from app.db import get_db
    from app.main import app

    def _override():
        s = route_db()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    yield TestClient(app, base_url="https://testserver")
    app.dependency_overrides.clear()


@pytest.fixture
def turnstile_on(monkeypatch):
    from app.config import settings
    from app.services import turnstile_service

    monkeypatch.setattr(settings, "turnstile_site_key", "1x-site")
    monkeypatch.setattr(settings, "turnstile_secret_key", "1x-secret")
    monkeypatch.setattr(turnstile_service, "configured", lambda: True)
    monkeypatch.setattr(turnstile_service, "verify", lambda token, ip=None: True)


def _csrf(client: TestClient, path: str = "/leden/mila/vraag") -> str:
    page = client.get(path)
    assert page.status_code == 200
    return re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)


def _post(client, data, htmx=True):
    payload = {
        "csrf_token": _csrf(client),
        "name": GOOD["name"],
        "email": GOOD["email"],
        "topic": "trainingen",
        "message": GOOD["message"],
        "consent": "1",
        "started": str(int(time.time()) - 30),
        "cf-turnstile-response": "tok",
        **data,
    }
    headers = {"HX-Request": "true"} if htmx else {}
    return client.post("/leden/mila/vraag", data=payload, headers=headers)


def test_profile_shows_inquiry_section_and_beacon_link(client, turnstile_on):
    html = client.get("/leden/mila").text
    assert 'id="vraag"' in html and "Werk met Mila." in html
    assert 'data-inquiry-topic="trainingen"' in html  # beacon → formulier
    assert "challenges.cloudflare.com/turnstile" in html


def test_profile_without_turnstile_shows_unavailable(client):
    html = client.get("/leden/mila").text
    assert "kan op dit moment even niet" in html
    assert 'name="website"' not in html


def test_post_happy_path_htmx(client, turnstile_on, route_db, notified):
    resp = _post(client, {})
    assert resp.status_code == 200 and "Je vraag is bij Mila." in resp.text
    assert "<!DOCTYPE" not in resp.text  # fragment
    with route_db() as s:
        assert s.scalar(select(func.count(Inquiry.id))) == 1
        assert s.scalar(select(func.count(AiSpendLog.id))) == 0  # nul AI
    assert len(notified) == 1


def test_post_without_js_renders_full_page(client, turnstile_on):
    resp = _post(client, {}, htmx=False)
    assert (
        resp.status_code == 200
        and "<!DOCTYPE html>" in resp.text
        and "Je vraag is bij" in resp.text
    )


def test_post_validation_error_keeps_input(client, turnstile_on):
    resp = _post(client, {"message": "kort"})
    assert resp.status_code == 422 and "Vertel iets meer" in resp.text
    assert "Sanne de Vries" in resp.text


def test_post_turnstile_fail(client, turnstile_on, monkeypatch, route_db):
    from app.services import turnstile_service

    monkeypatch.setattr(turnstile_service, "verify", lambda token, ip=None: False)
    resp = _post(client, {})
    assert resp.status_code == 422 and "mens" in resp.text
    with route_db() as s:
        assert s.scalar(select(func.count(Inquiry.id))) == 0


def test_post_honeypot_silent(client, turnstile_on, route_db):
    resp = _post(client, {"website": "http://spam"})
    assert resp.status_code == 200 and "Je vraag is bij" in resp.text
    with route_db() as s:
        assert s.scalar(select(func.count(Inquiry.id))) == 0


def test_members_only_profile_has_no_inquiry_page(client, turnstile_on):
    assert client.get("/leden/bo/vraag").status_code == 404
    csrf = _csrf(client)
    resp = client.post("/leden/bo/vraag", data={"csrf_token": csrf, "name": "x"})
    assert resp.status_code == 404


def _login(client, member_id: int):
    from tests.test_uat_coverage import _session_cookie

    client.cookies.set("session", _session_cookie({"member_id": member_id}))


def test_inbox_and_detail_for_owner(client, turnstile_on, route_db):
    _post(client, {})
    with route_db() as s:
        owner_id = s.scalar(select(Member.id).where(Member.email == "maker@example.com"))
        iq_id = s.scalar(select(Inquiry.id))
    _login(client, owner_id)
    inbox = client.get("/aanvragen")
    assert inbox.status_code == 200 and "Sanne de Vries" in inbox.text
    detail = client.get(f"/aanvragen/{iq_id}")
    assert detail.status_code == 200 and "mailto:sanne@bureau.nl" in detail.text
    with route_db() as s:
        assert s.get(Inquiry, iq_id).status == InquiryStatus.read


def test_detail_of_other_member_is_404(client, turnstile_on, route_db):
    _post(client, {})
    with route_db() as s:
        other_id = s.scalar(select(Member.id).where(Member.email == "besloten@example.com"))
        iq_id = s.scalar(select(Inquiry.id))
    _login(client, other_id)
    assert client.get(f"/aanvragen/{iq_id}").status_code == 404


def test_owner_is_redirected_from_own_inquiry_page(client, turnstile_on, route_db):
    with route_db() as s:
        owner_id = s.scalar(select(Member.id).where(Member.email == "maker@example.com"))
    _login(client, owner_id)
    resp = client.get("/leden/mila/vraag", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/aanvragen"
    assert 'id="vraag"' not in client.get("/leden/mila").text
