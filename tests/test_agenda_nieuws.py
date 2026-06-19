"""Tests voor agenda + nieuws (Post): plaatsen, validatie, rate-limit, sortering,
admin-moderatie, en de AVG-nullify bij accountverwijdering.

Eén holistische ``Post``-entiteit met ``kind`` ∈ {event, nieuws}. Kernen die we
bewaken:
- elk goedgekeurd lid plaatst direct zichtbaar (geen wachtrij);
- events sorteren aankomend-eerst, nieuws nieuwste-eerst;
- ``added_by_id`` is SET NULL → een gewist account laat de bijdrage staan.

Geen netwerk: ``current_member`` wordt overschreven; een wegwerp-engine per test
houdt rijen hermetisch (spiegelt test_ideas).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests._route_helpers import csrf_token, make_route_engine


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
    from app.models import Member, MemberRole, MemberStatus

    s = SessionTest()
    member = Member(email="a@example.com", name="Lid A", status=MemberStatus.approved)
    admin = Member(
        email="admin@example.com",
        name="Beheerder",
        status=MemberStatus.approved,
        role=MemberRole.admin,
    )
    pending = Member(email="p@example.com", name="Wacht", status=MemberStatus.pending)
    s.add_all([member, admin, pending])
    s.commit()
    ids = {"member": member.id, "admin": admin.id, "pending": pending.id}
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
# Auth-poort                                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", ["/agenda", "/nieuws"])
def test_anonymous_redirects_to_login(make_client, path):
    client = make_client(None)
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


@pytest.mark.parametrize("path", ["/agenda", "/nieuws"])
def test_approved_member_sees_page(make_client, seed, path):
    client = make_client(seed["member"])
    resp = client.get(path)
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# Agenda — plaatsen + validatie                                               #
# --------------------------------------------------------------------------- #
def test_submit_event_persists(make_client, seed, SessionTest):
    from app.models import EventFrequency, Post, PostKind

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        "/agenda",
        data={
            "title": "Aimelo meetup",
            "frequency": "wekelijks",
            "location": "Almelo",
            "cadence_note": "elke woensdag",
            "url": "https://aimelo.nl",
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "Aimelo meetup" in resp.text

    s = SessionTest()
    try:
        rows = s.query(Post).all()
        assert len(rows) == 1
        assert rows[0].kind == PostKind.event
        assert rows[0].frequency == EventFrequency.wekelijks
        assert rows[0].added_by_id == seed["member"]
    finally:
        s.close()


def test_submit_event_without_title_is_rejected(make_client, seed, SessionTest):
    from app.models import Post

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        "/agenda",
        data={"title": "", "frequency": "wekelijks"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400
    s = SessionTest()
    try:
        assert s.query(Post).count() == 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Nieuws — plaatsen + validatie (link verplicht)                              #
# --------------------------------------------------------------------------- #
def test_submit_news_persists(make_client, seed, SessionTest):
    from app.models import NewsRole, Post, PostKind

    client = make_client(seed["member"])
    token = csrf_token(client, "/nieuws")
    resp = client.post(
        "/nieuws",
        data={
            "title": "Interview met een bouwer",
            "url": "https://example.com/artikel",
            "role": "geinterviewd",
            "source": "Emerce",
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "Interview met een bouwer" in resp.text

    s = SessionTest()
    try:
        rows = s.query(Post).all()
        assert len(rows) == 1
        assert rows[0].kind == PostKind.nieuws
        assert rows[0].role == NewsRole.geinterviewd
    finally:
        s.close()


def test_submit_news_without_url_is_rejected(make_client, seed, SessionTest):
    from app.models import Post

    client = make_client(seed["member"])
    token = csrf_token(client, "/nieuws")
    resp = client.post(
        "/nieuws",
        data={"title": "Zonder link", "url": ""},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400
    s = SessionTest()
    try:
        assert s.query(Post).count() == 0
    finally:
        s.close()


def test_submit_news_with_bad_url_is_rejected(make_client, seed):
    client = make_client(seed["member"])
    token = csrf_token(client, "/nieuws")
    resp = client.post(
        "/nieuws",
        data={"title": "Rare link", "url": "javascript:alert(1)"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Rate-limit (gedeeld over events + nieuws)                                    #
# --------------------------------------------------------------------------- #
def test_rate_limit_blocks_after_budget(make_client, seed, SessionTest, monkeypatch):
    from app.config import settings
    from app.models import Post

    monkeypatch.setattr(settings, "rate_limit_post_per_hour", 2)
    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    for i in range(2):
        r = client.post(
            "/agenda",
            data={"title": f"Event {i}", "frequency": "eenmalig"},
            headers={"X-CSRF-Token": token},
        )
        assert r.status_code == 200
    # derde overschrijdt het budget
    r = client.post(
        "/nieuws",
        data={"title": "Te veel", "url": "https://example.com"},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 429
    s = SessionTest()
    try:
        assert s.query(Post).count() == 2  # de geblokkeerde is niet geschreven
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Admin-moderatie — verbergen filtert uit de lijst                            #
# --------------------------------------------------------------------------- #
def test_admin_hide_removes_from_list(make_client, seed, SessionTest):
    from app.models import Post, PostKind

    s = SessionTest()
    post = Post(added_by_id=seed["member"], kind=PostKind.nieuws, title="Verbergmij",
                url="https://example.com")
    s.add(post)
    s.commit()
    post_id = post.id
    s.close()

    admin = make_client(seed["admin"])
    token = csrf_token(admin, "/nieuws")
    resp = admin.post(
        f"/admin/posts/{post_id}/verberg", headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 200

    # lid ziet 'm niet meer
    member = make_client(seed["member"])
    page = member.get("/nieuws")
    assert "Verbergmij" not in page.text


def test_non_admin_cannot_hide(make_client, seed, SessionTest):
    from app.models import Post, PostKind

    s = SessionTest()
    post = Post(added_by_id=seed["member"], kind=PostKind.event, title="X")
    s.add(post)
    s.commit()
    post_id = post.id
    s.close()

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        f"/admin/posts/{post_id}/verberg",
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303, 403)


# --------------------------------------------------------------------------- #
# Service-laag — sortering                                                     #
# --------------------------------------------------------------------------- #
def test_list_events_upcoming_first(SessionTest, seed):
    from app.models import EventFrequency, Post, PostKind
    from app.security import utcnow
    from app.services import post_service

    now = utcnow()
    s = SessionTest()
    soon = Post(kind=PostKind.event, title="Binnenkort", frequency=EventFrequency.eenmalig,
                next_at=now + timedelta(days=2))
    later = Post(kind=PostKind.event, title="Later", frequency=EventFrequency.eenmalig,
                 next_at=now + timedelta(days=20))
    past = Post(kind=PostKind.event, title="Verleden", frequency=EventFrequency.eenmalig,
                next_at=now - timedelta(days=5))
    undated = Post(kind=PostKind.event, title="Doorlopend",
                   frequency=EventFrequency.doorlopend, next_at=None)
    s.add_all([past, later, undated, soon])
    s.commit()
    events = post_service.list_events(s)
    titles = [e.title for e in events]
    # aankomend (soon < later) eerst, dan zonder-datum, dan verleden achteraan
    assert titles.index("Binnenkort") < titles.index("Later")
    assert titles.index("Later") < titles.index("Verleden")
    assert titles.index("Doorlopend") < titles.index("Verleden")
    s.close()


def test_list_news_newest_first(SessionTest):
    from app.models import NewsRole, Post, PostKind
    from app.security import utcnow
    from app.services import post_service

    now = utcnow()
    s = SessionTest()
    oud = Post(kind=PostKind.nieuws, title="Oud", url="https://a", role=NewsRole.gedeeld,
               published_at=now - timedelta(days=30))
    nieuw = Post(kind=PostKind.nieuws, title="Nieuw", url="https://b", role=NewsRole.gedeeld,
                 published_at=now - timedelta(days=1))
    s.add_all([oud, nieuw])
    s.commit()
    items = post_service.list_news(s)
    assert [i.title for i in items] == ["Nieuw", "Oud"]
    s.close()


def test_hidden_excluded_from_lists(SessionTest):
    from app.models import NewsRole, Post, PostKind
    from app.services import post_service

    s = SessionTest()
    visible = Post(kind=PostKind.nieuws, title="Zichtbaar", url="https://a",
                   role=NewsRole.gedeeld)
    hidden = Post(kind=PostKind.nieuws, title="Verborgen", url="https://b",
                  role=NewsRole.gedeeld, hidden=True)
    s.add_all([visible, hidden])
    s.commit()
    titles = [i.title for i in post_service.list_news(s)]
    assert titles == ["Zichtbaar"]
    s.close()


# --------------------------------------------------------------------------- #
# AVG — accountverwijdering laat de bijdrage staan (added_by → NULL)          #
# --------------------------------------------------------------------------- #
def test_account_deletion_nullifies_post_author(SessionTest, seed):
    from app.models import Member, Post, PostKind
    from app.services.account_deletion import delete_member_completely

    s = SessionTest()
    post = Post(added_by_id=seed["member"], kind=PostKind.event, title="Blijft staan")
    s.add(post)
    s.commit()
    post_id = post.id

    member = s.get(Member, seed["member"])
    delete_member_completely(s, member)
    s.commit()

    survivor = s.get(Post, post_id)
    assert survivor is not None  # community-waarde blijft
    assert survivor.added_by_id is None  # geen anker meer naar het gewiste lid
    s.close()


# --------------------------------------------------------------------------- #
# Helpers — relatieve_tijd / nl_datum                                         #
# --------------------------------------------------------------------------- #
def test_relatieve_tijd_buckets():
    from app.security import utcnow
    from app.services.post_service import relatieve_tijd

    now = utcnow()
    assert relatieve_tijd(now, now=now) == "vandaag"
    assert relatieve_tijd(now + timedelta(days=1), now=now) == "morgen"
    assert relatieve_tijd(now + timedelta(days=3), now=now) == "over 3 dagen"
    assert relatieve_tijd(now - timedelta(days=2), now=now) == "geweest"
    assert relatieve_tijd(None) == ""


def test_nl_datum_format():
    from datetime import datetime

    from app.services.post_service import nl_datum

    assert nl_datum(datetime(2026, 6, 24, 18, 0)) == "24 jun 2026"
    assert nl_datum(None) == ""
