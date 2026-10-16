"""Je vindbaarheid (PRD hub §4.4): anonieme dagtellers + het dashboard."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.models import (
    Base,
    Member,
    MemberRole,
    MemberStatus,
    Offering,
    OfferingKind,
    Profile,
    ProfileStatDay,
    Visibility,
)
from app.security import utcnow
from app.services import account_deletion, directory_service, stats_service
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15"


@pytest.mark.parametrize(
    "ua,expected",
    [
        (BROWSER, "view"),
        ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2)", "ai_fetch"),
        ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "ai_fetch"),
        ("Mozilla/5.0 (compatible; PerplexityBot/1.0)", "ai_fetch"),
        ("Mozilla/5.0 (compatible; Googlebot/2.1)", None),
        ("curl/8.4.0", None),
        ("python-httpx/0.27", None),
        ("", None),
    ],
)
def test_classify_agent(ua, expected):
    assert stats_service.classify_agent(ua) == expected


def test_record_accumulates_per_day_and_kind(db, make_member, make_profile):
    p = make_profile(make_member())
    today = utcnow().date()
    for _ in range(3):
        stats_service.record(db, p.id, "view", day=today)
    stats_service.record(db, p.id, "ai_fetch", day=today)
    stats_service.record(db, p.id, "view", day=today - timedelta(days=1))
    rows = {(r.day, r.kind): r.count for r in db.scalars(select(ProfileStatDay))}
    assert rows[(today, "view")] == 3 and rows[(today, "ai_fetch")] == 1
    s = stats_service.summary(db, p.id, p.member_id, today=today)
    assert s.views == 4 and s.ai_fetches == 1 and s.peak == 3
    assert len(s.days) == stats_service.WINDOW_DAYS and s.days[-1] == (today, 3)


def test_summary_ignores_older_than_window(db, make_member, make_profile):
    p = make_profile(make_member())
    today = utcnow().date()
    stats_service.record(db, p.id, "view", day=today - timedelta(days=40))
    assert stats_service.summary(db, p.id, p.member_id, today=today).views == 0


def test_account_deletion_removes_stats(db, make_member, make_profile):
    m = make_member()
    p = make_profile(m)
    stats_service.record(db, p.id, "view")
    account_deletion.delete_member_completely(db, m)
    assert db.scalar(select(func.count(ProfileStatDay.id))) == 0


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
        m = Member(email="mila@x.nl", name="Mila Maker", status=MemberStatus.approved)
        admin = Member(email="a@x.nl", name="Admin", status=MemberStatus.approved,
                       role=MemberRole.admin)
        closed = Member(email="bo@x.nl", name="Bo", status=MemberStatus.approved)
        s.add_all([m, admin, closed])
        s.flush()
        p = Profile(member_id=m.id, slug="mila", display_name="Mila Maker",
                    visibility=Visibility.public, headline="AI-trainer", open_to=["trainingen"])
        s.add(p)
        s.add(Profile(member_id=closed.id, slug="bo", display_name="Bo",
                      visibility=Visibility.members))
        s.flush()
        s.add(Offering(profile_id=p.id, title="RAG-workshop", kind=OfferingKind.workshop,
                       slug="rag"))
        s.commit()
    yield Session
    eng.dispose()


@pytest.fixture
def client(route_db):
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


def _login(client, email, route_db):
    from tests.test_uat_coverage import _session_cookie

    with route_db() as s:
        mid = s.scalar(select(Member.id).where(Member.email == email))
    client.cookies.set("session", _session_cookie({"member_id": mid}))


def _counts(route_db):
    with route_db() as s:
        return {r.kind: r.count for r in s.scalars(select(ProfileStatDay))}


def test_profile_view_counts_humans_and_ai_not_owner_or_admin(client, route_db):
    client.get("/leden/mila", headers={"User-Agent": BROWSER})
    client.get("/leden/mila", headers={"User-Agent": "ClaudeBot/1.0"})
    client.get("/leden/mila", headers={"User-Agent": "curl/8"})
    assert _counts(route_db) == {"view": 1, "ai_fetch": 1}
    _login(client, "mila@x.nl", route_db)
    client.get("/leden/mila", headers={"User-Agent": BROWSER})
    _login(client, "a@x.nl", route_db)
    client.get("/leden/mila", headers={"User-Agent": BROWSER})
    assert _counts(route_db) == {"view": 1, "ai_fetch": 1}


def test_mcp_search_counts_hits(route_db):
    with route_db() as s:
        directory_service.search_public(s, "workshop")
    assert _counts(route_db) == {"mcp_hit": 1}


def test_dashboard_public_member(client, route_db):
    client.get("/leden/mila", headers={"User-Agent": BROWSER})
    _login(client, "mila@x.nl", route_db)
    html = client.get("/profiel/vindbaarheid").text
    assert "Je vindbaarheid." in html
    assert 'class="vb-tile__n">1</span><span class="vb-tile__l">keer bekeken door mensen' in html
    assert "Gids Trainers" in html  # staat in de trainers-gids
    assert "/leden/mila/vraag" in html  # zo leest een AI je
    assert "Je profiel is besloten" not in html


def test_dashboard_closed_member_gets_nudge(client, route_db):
    _login(client, "bo@x.nl", route_db)
    html = client.get("/profiel/vindbaarheid").text
    assert "Je profiel is besloten" in html and "Zet je profiel op openbaar" in html
    assert "Gids " not in html


def test_view_via_home_counts_separately(client, route_db):
    client.get("/leden/mila?via=home", headers={"User-Agent": BROWSER})
    client.get("/leden/mila?via=home", headers={"User-Agent": "ClaudeBot/1.0"})
    assert _counts(route_db) == {"view": 1, "via_home": 1, "ai_fetch": 1}
    _login(client, "mila@x.nl", route_db)
    assert "waarvan 1 via de voorpagina" in client.get("/profiel/vindbaarheid").text
