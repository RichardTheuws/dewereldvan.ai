"""Tests voor "De Briefing" (doc 02) — AI-gecureerd nieuws met mens-in-de-lus.

Geen netwerk, geen Anthropic-key:
- De curatie-service draait met een in-memory fake Anthropic-client die ÉÉN
  ``record_news_item``-tool-use teruggeeft (gespiegeld van test_footprint_discovery).
- De service-laag wordt direct op de rollback-geïsoleerde ``db``-fixture getest.
- De admin-routes draaien op een wegwerp-engine (gespiegeld van test_feedback) zodat
  hun commits niet lekken; ``current_member`` wordt overschreven voor de auth-staat.

Dekt: migratie-defaults (lid-bijdrage = live/member), ``create_curated_news``
idempotent op url, review-transities (approve→live, reject→rejected) + AuditLog,
``list_briefing`` splitst deze-week vs archief, ``list_pending_review`` toont alleen
pending, pending verschijnt NOOIT op de publieke nieuws-route, noindex/reduced-motion,
en de admin-route keurt goed/af via htmx.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.models import (
    AuditAction,
    AuditLog,
    MemberRole,
    MemberStatus,
    PostReviewState,
    PostSourceKind,
)
from app.security import naive_utc, utcnow
from app.services import news_curation_service, post_service
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests._route_helpers import csrf_token, make_route_engine


# --------------------------------------------------------------------------- #
# Fake Anthropic met een record_news_item-tool-use (streaming)                #
# --------------------------------------------------------------------------- #
class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self):
        return dict(self.__dict__)


class _FakeMsg:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _FakeStream:
    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        return iter(self._owner.script[self._owner.call_idx].get("deltas", []))

    def get_final_message(self):
        owner = self._owner
        step = owner.script[owner.call_idx]
        owner.call_idx += 1
        return _FakeMsg(step["stop_reason"], step["content"])


class _FakeMessages:
    def __init__(self, owner):
        self._owner = owner

    def stream(self, **kwargs):
        self._owner.stream_kwargs.append(kwargs)
        return _FakeStream(self._owner)


class FakeAnthropic:
    """Speelt een lijst van ronde-stappen af (één per ``stream(...)``-call)."""

    def __init__(self, script):
        self.script = script
        self.call_idx = 0
        self.stream_kwargs: list[dict] = []
        self.messages = _FakeMessages(self)


def _items_block(items):
    return _Block(type="tool_use", name="record_news_item", id="t1",
                  input={"items": items})


# --------------------------------------------------------------------------- #
# Migratie-defaults: een lid-bijdrage blijft live/member                       #
# --------------------------------------------------------------------------- #
def test_member_news_is_live_member(db, make_member):
    member = make_member()
    post = post_service.create_news(
        db, member=member, title="Lid deelt iets", url="https://lid.example/a"
    )
    assert post.review_state == PostReviewState.live
    assert post.source_kind == PostSourceKind.member
    assert post.ai_take is None and post.ai_relevance is None


# --------------------------------------------------------------------------- #
# create_curated_news: voorstel = pending_review (nooit live) + idempotent     #
# --------------------------------------------------------------------------- #
def test_curated_news_starts_pending(db):
    post = post_service.create_curated_news(
        db, title="AI Act handhaving", url="https://ap.example/aiact",
        ai_take="Raakt je labelling vanaf augustus.", ai_relevance=88,
    )
    # MENS-IN-DE-LUS: nooit live bij aanmaken.
    assert post.review_state == PostReviewState.pending_review
    assert post.source_kind == PostSourceKind.ai_curated
    assert post.ai_relevance == 88
    assert post.briefing_week is not None


def test_curated_news_idempotent_on_url(db):
    a = post_service.create_curated_news(
        db, title="X", url="https://dup.example/1", ai_take="why", ai_relevance=80
    )
    b = post_service.create_curated_news(
        db, title="X (opnieuw)", url="https://dup.example/1", ai_take="why2",
        ai_relevance=90,
    )
    assert a.id == b.id  # dedup: geen tweede rij
    rows = db.scalars(
        select(post_service.Post).where(post_service.Post.url == "https://dup.example/1")
    ).all()
    assert len(rows) == 1


# --------------------------------------------------------------------------- #
# Review-transities: approve -> live, reject -> rejected (+ AuditLog)          #
# --------------------------------------------------------------------------- #
def test_approve_news_goes_live_with_audit(db, make_member):
    admin = make_member(email="admin@x.example", role=MemberRole.admin)
    post = post_service.create_curated_news(
        db, title="Goedkeurbaar", url="https://ok.example/1", ai_take="why",
        ai_relevance=85,
    )
    post_service.approve_news(db, post, actor=admin)
    assert post.review_state == PostReviewState.live
    log = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.news_approved))
    assert log is not None and log.actor_member_id == admin.id


def test_reject_news_is_rejected_with_audit(db, make_member):
    admin = make_member(email="admin2@x.example", role=MemberRole.admin)
    post = post_service.create_curated_news(
        db, title="Weigerbaar", url="https://no.example/1", ai_take="why",
        ai_relevance=72,
    )
    post_service.reject_news(db, post, actor=admin)
    assert post.review_state == PostReviewState.rejected
    log = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.news_rejected))
    assert log is not None


# --------------------------------------------------------------------------- #
# list_briefing splitst deze-week vs archief                                   #
# --------------------------------------------------------------------------- #
def test_list_briefing_splits_this_week_vs_archive(db, make_member):
    member = make_member()
    now = naive_utc(utcnow())
    this_week = post_service.iso_week_anchor(now)
    last_week = this_week - timedelta(days=7)

    # Deze week: een goedgekeurd AI-item.
    cur = post_service.create_curated_news(
        db, title="Deze week", url="https://w.example/now", ai_take="why",
        ai_relevance=90, briefing_week=this_week,
    )
    post_service.approve_news(db, cur, actor=member)
    # Vorige week: ook live (via archief-anker).
    old = post_service.create_curated_news(
        db, title="Vorige week", url="https://w.example/old", ai_take="why",
        ai_relevance=90, briefing_week=last_week,
    )
    post_service.approve_news(db, old, actor=member)
    db.flush()

    briefing = post_service.list_briefing(db, now=now)
    titles_now = [p.title for p in briefing.briefing_this_week]
    titles_arch = [p.title for p in briefing.archief]
    assert "Deze week" in titles_now
    assert "Vorige week" in titles_arch
    assert "Vorige week" not in titles_now


# --------------------------------------------------------------------------- #
# list_pending_review toont alleen pending; publiek nooit                      #
# --------------------------------------------------------------------------- #
def test_pending_only_in_review_list_never_public(db, make_member):
    member = make_member()
    pending = post_service.create_curated_news(
        db, title="In review", url="https://r.example/p", ai_take="why",
        ai_relevance=80,
    )
    approved = post_service.create_curated_news(
        db, title="Live nu", url="https://r.example/live", ai_take="why",
        ai_relevance=80,
    )
    post_service.approve_news(db, approved, actor=member)
    db.flush()

    pend = [p.id for p in post_service.list_pending_review(db)]
    assert pending.id in pend
    assert approved.id not in pend

    public = [p.id for p in post_service.list_news(db)]
    # Mens-in-de-lus-poort: pending_review komt NOOIT in de publieke lijst.
    assert pending.id not in public
    assert approved.id in public


def test_rejected_never_public(db, make_member):
    member = make_member()
    rej = post_service.create_curated_news(
        db, title="Geweigerd", url="https://r.example/x", ai_take="why",
        ai_relevance=80,
    )
    post_service.reject_news(db, rej, actor=member)
    db.flush()
    assert rej.id not in [p.id for p in post_service.list_news(db)]
    assert rej.id not in [p.id for p in post_service.list_pending_review(db)]


# --------------------------------------------------------------------------- #
# Curatie-service: fake AI -> gegronde, drempel-gepoorte kandidaten            #
# --------------------------------------------------------------------------- #
def test_curate_applies_threshold_and_grounding(db, monkeypatch):
    monkeypatch.setattr(news_curation_service.settings, "ai_enrich_enabled", True)
    fake = FakeAnthropic([
        {
            "stop_reason": "end_turn",
            "content": [_items_block([
                # Sterk genoeg + echte URL -> blijft.
                {"title": "AI Act NL", "url": "https://ap.example/aiact",
                 "source": "AP", "ai_take": "Raakt je labelling.", "ai_relevance": 88},
                # Onder de drempel -> gedropt.
                {"title": "Zwak", "url": "https://x.example/zwak",
                 "ai_take": "marginaal", "ai_relevance": 40},
                # Geen echte URL -> grounding-poort dropt 'm.
                {"title": "Geen url", "url": "not-a-url",
                 "ai_take": "iets", "ai_relevance": 99},
            ])],
        },
    ])
    cands = news_curation_service.curate(db, client=fake)
    assert len(cands) == 1
    assert cands[0].url == "https://ap.example/aiact"
    assert cands[0].ai_relevance == 88


def test_curate_gated_off_returns_empty(db, monkeypatch):
    monkeypatch.setattr(news_curation_service.settings, "ai_enrich_enabled", False)
    assert news_curation_service.curate(db, client=FakeAnthropic([])) == []


def test_curate_pause_turn_loop(db, monkeypatch):
    """De server-tool-loop: een pause_turn-ronde gevolgd door de eindronde."""
    monkeypatch.setattr(news_curation_service.settings, "ai_enrich_enabled", True)
    fake = FakeAnthropic([
        {"stop_reason": "pause_turn",
         "content": [_Block(type="server_tool_use", name="web_search", id="s1",
                            input={"query": "AI Act NL"})]},
        {"stop_reason": "end_turn",
         "content": [_items_block([
             {"title": "NA pauze", "url": "https://ap.example/na",
              "ai_take": "why", "ai_relevance": 80},
         ])]},
    ])
    cands = news_curation_service.curate(db, client=fake)
    assert len(cands) == 1 and cands[0].title == "NA pauze"
    assert fake.call_idx == 2  # twee stream-rondes


# --------------------------------------------------------------------------- #
# Publieke nieuws-route: noindex + pending nooit zichtbaar                      #
# --------------------------------------------------------------------------- #
@pytest.fixture
def SessionTest():
    from sqlalchemy.orm import sessionmaker

    eng = make_route_engine()
    yield sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    eng.dispose()


@pytest.fixture
def make_client(SessionTest):
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

    def _factory(member_id: int | None):
        def _override_current_member(db: Session = Depends(get_db)):
            return db.get(Member, member_id) if member_id is not None else None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


@pytest.fixture
def seed(SessionTest):
    from app.models import Member

    s = SessionTest()
    admin = Member(email="admin@dewereldvan.ai", name="Beheer",
                   status=MemberStatus.approved, role=MemberRole.admin)
    member = Member(email="lid@example.com", name="Lid",
                    status=MemberStatus.approved, role=MemberRole.member)
    s.add_all([admin, member])
    s.commit()
    ids = {"admin": admin.id, "member": member.id}
    s.close()
    return ids


def test_public_nieuws_is_noindex_and_hides_pending(make_client, seed, SessionTest):
    # Eén pending kandidaat + één live item.
    s = SessionTest()
    post_service.create_curated_news(
        s, title="VERBORGEN KANDIDAAT", url="https://r.example/hidden",
        ai_take="why", ai_relevance=85,
    )
    live = post_service.create_curated_news(
        s, title="ZICHTBAAR LIVE", url="https://r.example/visible",
        ai_take="Dit is de duiding.", ai_relevance=85,
    )
    from app.models import Member

    admin = s.get(Member, seed["admin"])
    post_service.approve_news(s, live, actor=admin)
    s.commit()
    s.close()

    client = make_client(seed["member"])
    resp = client.get("/nieuws")
    assert resp.status_code == 200
    assert "noindex" in resp.text  # login-gated pagina
    assert "ZICHTBAAR LIVE" in resp.text
    assert "VERBORGEN KANDIDAAT" not in resp.text  # pending nooit publiek
    # De AI-duiding van een live item is zichtbaar.
    assert "Dit is de duiding." in resp.text


# --------------------------------------------------------------------------- #
# Admin-route: shortlist + goedkeuren/weigeren via htmx                         #
# --------------------------------------------------------------------------- #
def test_admin_shortlist_requires_admin(make_client, seed):
    member_client = make_client(seed["member"])
    assert member_client.get("/admin/nieuws").status_code == 403


def test_admin_approve_via_htmx(make_client, seed, SessionTest):
    s = SessionTest()
    cand = post_service.create_curated_news(
        s, title="Te keuren", url="https://r.example/keur", ai_take="why",
        ai_relevance=90,
    )
    cand_id = cand.id
    s.commit()
    s.close()

    admin_client = make_client(seed["admin"])
    token = csrf_token(admin_client, "/admin/nieuws")
    resp = admin_client.post(
        f"/admin/nieuws/{cand_id}/keur-goed", headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 200
    assert "Goedgekeurd" in resp.text

    # Server-side: het item staat nu live (publiek zichtbaar).
    s2 = SessionTest()
    refreshed = s2.get(post_service.Post, cand_id)
    assert refreshed.review_state == PostReviewState.live
    s2.close()


def test_admin_reject_via_htmx(make_client, seed, SessionTest):
    s = SessionTest()
    cand = post_service.create_curated_news(
        s, title="Te weigeren", url="https://r.example/weiger", ai_take="why",
        ai_relevance=72,
    )
    cand_id = cand.id
    s.commit()
    s.close()

    admin_client = make_client(seed["admin"])
    token = csrf_token(admin_client, "/admin/nieuws")
    resp = admin_client.post(
        f"/admin/nieuws/{cand_id}/weiger", headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 200

    s2 = SessionTest()
    refreshed = s2.get(post_service.Post, cand_id)
    assert refreshed.review_state == PostReviewState.rejected
    s2.close()
