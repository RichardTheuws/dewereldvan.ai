"""Zoeken over de hub (PRD voordeur §3.1): makers, events, nieuws — nul AI, en
alleen wat een bezoeker mag zien."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.models import (
    AiSpendLog,
    Base,
    EventFrequency,
    Member,
    MemberStatus,
    Offering,
    OfferingKind,
    Post,
    PostKind,
    PostReviewState,
    PostSourceKind,
    Profile,
    Tag,
    Visibility,
)
from app.security import naive_utc, utcnow
from app.services import search_service
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


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
    now = naive_utc(utcnow())
    with Session() as s:
        def member(email, name, vis, **kw):
            m = Member(email=email, name=name, status=MemberStatus.approved)
            s.add(m)
            s.flush()
            p = Profile(member_id=m.id, slug=name.split()[0].lower(), display_name=name,
                        visibility=vis, **kw)
            s.add(p)
            s.flush()
            return m, p

        _, mila = member("m@x.nl", "Mila Maker", Visibility.public, headline="AI-trainer zorg")
        mila.tags.append(Tag(slug="rag", name="RAG"))
        s.add(Offering(profile_id=mila.id, title="Workshop RAG voor de zorg",
                       kind=OfferingKind.workshop))
        member("b@x.nl", "Bo Besloten", Visibility.members, headline="Geheime RAG-expert")
        member("s@x.nl", "Sem Sectie", Visibility.public, headline="Bouwer",
               makes_summary="RAG-pipelines", public_sections=["bio"])
        bo_m = s.scalar(select(Member).where(Member.email == "b@x.nl"))

        def post(**kw):
            s.add(Post(review_state=kw.pop("state", PostReviewState.live), **kw))

        post(kind=PostKind.event, title="RAG meetup Utrecht", location="Utrecht",
             next_at=now + timedelta(days=5), frequency=EventFrequency.eenmalig)
        post(kind=PostKind.event, title="RAG meetup vorig jaar", location="Utrecht",
             next_at=now - timedelta(days=5), frequency=EventFrequency.eenmalig)
        post(kind=PostKind.event, title="RAG wachtrij-event", next_at=now + timedelta(days=9),
             state=PostReviewState.pending_review)
        post(kind=PostKind.nieuws, title="Nieuw RAG-model", url="https://n.example/1",
             source_kind=PostSourceKind.ai_curated)
        post(kind=PostKind.nieuws, title="RAG-nieuws van besloten lid",
             url="https://n.example/2", added_by_id=bo_m.id)
        post(kind=PostKind.nieuws, title="Verborgen RAG", url="https://n.example/3", hidden=True)
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


def test_search_finds_only_what_a_visitor_may_see(route_db):
    with route_db() as s:
        res = search_service.search(s, "rag")
        assert [p.display_name for p in res.makers] == ["Mila Maker"]  # besloten (blok) weg
        assert [e.title for e in res.events] == ["RAG meetup Utrecht"]  # verlopen + pending weg
        assert [n.title for n in res.news] == ["Nieuw RAG-model"]  # besloten lid + verborgen weg
        assert res.totals == {"makers": 1, "events": 1, "news": 1}


def test_search_is_and_over_words_and_case_insensitive(route_db):
    with route_db() as s:
        assert search_service.search(s, "RAG utrecht").events
        assert not search_service.search(s, "rag amsterdam").events


@pytest.mark.parametrize("q", ["", " ", "a", "x " * 3])
def test_short_query_does_not_search(route_db, q):
    with route_db() as s:
        res = search_service.search(s, q)
        assert res.empty and res.totals == {}


def test_query_is_capped():
    assert len(search_service.normalize_query("x" * 500)) == search_service.MAX_QUERY


def test_zoek_page_empty_state_is_indexable(client):
    html = client.get("/zoek").text
    assert "Wat zoek je?" in html and 'content="noindex"' not in html
    assert 'href="/gids/trainers"' in html


def test_zoek_results_page(client, route_db):
    html = client.get("/zoek", params={"q": "rag"}).text
    assert 'content="noindex"' in html
    assert "Mila Maker" in html and "Bo Besloten" not in html and "Geheime" not in html
    assert "RAG meetup Utrecht" in html and "vorig jaar" not in html
    assert "Nieuw RAG-model" in html and "besloten lid" not in html
    assert "/leden/mila/vraag" in html
    with route_db() as s:
        assert s.scalar(select(func.count(AiSpendLog.id))) == 0  # nul AI


def test_zoek_no_results(client):
    html = client.get("/zoek", params={"q": "astrologie"}).text
    assert "Niets gevonden" in html
