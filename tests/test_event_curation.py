"""Tests voor de agenda-curatie (plan Increment 3).

Geen netwerk: de Claude-stream wordt gemockt via ``FakeAnthropic`` (tools-loop
+ ``record_event_item``-tool-output). Kernen: gegronde mapping, de grondings-/
drempel-poorten, de auto-keur-beslissing, en idempotente persist (dedup op URL).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.services import event_curation_service as ec
from app.services import post_service
from tests._ai_helpers import FakeAnthropic
from tests._route_helpers import make_route_engine


@pytest.fixture
def route_engine():
    eng = make_route_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(bind=route_engine, autoflush=False, autocommit=False, future=True)


def _fake_with_items(items: list[dict]) -> FakeAnthropic:
    """FakeAnthropic die één turn record_event_item teruggeeft (end_turn)."""
    return FakeAnthropic(
        deltas=[""],
        stream_stop_reasons=["end_turn"],
        assistant_content=[
            {"type": "tool_use", "name": "record_event_item", "input": {"items": items}}
        ],
    )


# --------------------------------------------------------------------------- #
# _parse_dt — gegrond, nooit verzonnen tijd                                    #
# --------------------------------------------------------------------------- #
def test_parse_dt_variants():
    assert ec._parse_dt("2026-07-15T19:00") == datetime(2026, 7, 15, 19, 0)
    assert ec._parse_dt("2026-07-15") == datetime(2026, 7, 15, 0, 0)
    assert ec._parse_dt("") is None
    assert ec._parse_dt("binnenkort") is None
    assert ec._parse_dt(None) is None


# --------------------------------------------------------------------------- #
# auto_approvable — alleen zeker (hoge confidence + datum + locatie)           #
# --------------------------------------------------------------------------- #
def test_auto_approvable_rules():
    base = dict(title="X", url="https://e.nl", category="meetup", frequency="eenmalig")
    zeker = ec.EventCandidate(**base, confidence=90, next_at=datetime(2026, 7, 1, 18, 0), location="Almelo")
    assert ec.auto_approvable(zeker) is True
    # te lage confidence
    assert ec.auto_approvable(ec.EventCandidate(**base, confidence=70, next_at=datetime(2026, 7, 1), location="Almelo")) is False
    # geen datum
    assert ec.auto_approvable(ec.EventCandidate(**base, confidence=95, next_at=None, location="Almelo")) is False
    # geen locatie
    assert ec.auto_approvable(ec.EventCandidate(**base, confidence=95, next_at=datetime(2026, 7, 1), location=None)) is False


# --------------------------------------------------------------------------- #
# curate — gegronde mapping + poorten                                          #
# --------------------------------------------------------------------------- #
def test_curate_maps_grounded_event(SessionTest, monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    s = SessionTest()
    fake = _fake_with_items([{
        "title": "Aimelo meetup",
        "url": "https://aimelo.nl/events",
        "source": "Aimelo",
        "category": "coding",
        "frequency": "wekelijks",
        "date_iso": "2026-07-15T19:00",
        "location": "Almelo",
        "cadence_note": "elke woensdag",
        "description": "Wekelijkse AI-meetup.",
        "confidence": 92,
    }])
    out = ec.curate(s, client=fake)
    assert len(out) == 1
    c = out[0]
    assert c.title == "Aimelo meetup"
    assert c.url == "https://aimelo.nl/events"
    assert c.category == "coding"
    assert c.frequency == "wekelijks"
    assert c.next_at == datetime(2026, 7, 15, 19, 0)
    assert c.location == "Almelo"
    assert c.confidence == 92
    assert ec.auto_approvable(c) is True
    s.close()


def test_curate_drops_ungrounded_and_weak(SessionTest, monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    s = SessionTest()
    fake = _fake_with_items([
        {"title": "Geen URL", "url": "", "confidence": 95},          # geen echte URL
        {"title": "Te zwak", "url": "https://x.nl", "confidence": 40},  # < drempel
        {"title": "Goed", "url": "https://ok.nl", "confidence": 80, "category": "zomaar", "frequency": "ooit"},
    ])
    out = ec.curate(s, client=fake)
    assert [c.title for c in out] == ["Goed"]
    # onbekende enum-waarden → veilige defaults
    assert out[0].category == "meetup"
    assert out[0].frequency == "eenmalig"
    s.close()


def test_curate_ai_off_returns_empty(SessionTest, monkeypatch):
    monkeypatch.setattr(settings, "ai_enrich_enabled", False)
    s = SessionTest()
    # client mag niet eens aangeroepen worden
    out = ec.curate(s, client=_fake_with_items([{"title": "X", "url": "https://x.nl", "confidence": 99}]))
    assert out == []
    s.close()


# --------------------------------------------------------------------------- #
# create_curated_event — live/pending + dedup                                  #
# --------------------------------------------------------------------------- #
def test_create_curated_event_live_vs_pending_and_dedup(SessionTest):
    from app.models import EventCategory, EventFrequency, Post, PostKind, PostReviewState, PostSourceKind

    s = SessionTest()
    live = post_service.create_curated_event(
        s, title="Zeker event", url="https://zeker.nl", category="conferentie",
        frequency="eenmalig", confidence=90, live=True,
        next_at=datetime(2026, 8, 1, 9, 0), location="Amsterdam",
    )
    pending = post_service.create_curated_event(
        s, title="Twijfel event", url="https://twijfel.nl", category="meetup",
        frequency="wekelijks", confidence=65, live=False,
    )
    s.commit()
    assert live.review_state == PostReviewState.live
    assert live.source_kind == PostSourceKind.ai_curated
    assert live.category == EventCategory.conferentie
    assert live.ai_relevance == 90
    assert pending.review_state == PostReviewState.pending_review
    assert pending.frequency == EventFrequency.wekelijks

    # dedup op URL: zelfde URL → bestaand event terug, geen duplicaat
    again = post_service.create_curated_event(
        s, title="Dubbel", url="https://zeker.nl", confidence=99, live=True,
    )
    s.commit()
    assert again.id == live.id
    assert s.query(Post).filter(Post.kind == PostKind.event).count() == 2
    s.close()


def test_list_pending_events_sorted_and_excludes_live(SessionTest):
    s = SessionTest()
    post_service.create_curated_event(s, title="Live", url="https://a.nl", confidence=95, live=True,
                                      next_at=datetime(2026, 8, 1), location="X")
    post_service.create_curated_event(s, title="Lage conf", url="https://b.nl", confidence=62, live=False)
    post_service.create_curated_event(s, title="Hoge conf", url="https://c.nl", confidence=80, live=False)
    s.commit()
    pending = post_service.list_pending_events(s)
    assert [p.title for p in pending] == ["Hoge conf", "Lage conf"]  # confidence desc, geen live
    s.close()
