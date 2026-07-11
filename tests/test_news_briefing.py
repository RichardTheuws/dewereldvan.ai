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
    Tag,
    Tool,
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


def test_normalize_news_url_strips_tracking_and_slash():
    n = post_service._normalize_news_url
    # Tracking-params + fragment weg; overige query blijft.
    assert (
        n("https://ex.example/a?utm_source=x&id=7&fbclid=abc#top")
        == "https://ex.example/a?id=7"
    )
    # Trailing slash op het pad weg; root-slash blijft.
    assert n("https://ex.example/a/") == "https://ex.example/a"
    assert n("https://ex.example/") == "https://ex.example/"
    # Niet-absolute of lege input faalt veilig.
    assert n("") == ""
    assert n("not-a-url") == "not-a-url"


def test_curated_news_dedups_across_tracking_variants(db):
    """Dezelfde story bij dezelfde uitgever, alleen met campagne-tags, mag geen
    tweede rij worden — de URL-normalisatie vangt de bijna-duplicaat."""
    a = post_service.create_curated_news(
        db, title="Story", url="https://uitgever.example/artikel",
        ai_take="why", ai_relevance=80,
    )
    b = post_service.create_curated_news(
        db, title="Story (via nieuwsbrief)",
        url="https://uitgever.example/artikel?utm_source=nb&utm_medium=email",
        ai_take="why2", ai_relevance=90,
    )
    assert a.id == b.id  # genormaliseerd → één item
    # De opgeslagen URL is de gestripte, canonieke vorm.
    assert a.url == "https://uitgever.example/artikel"


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


def test_public_nieuws_is_indexable_and_hides_pending(make_client, seed, SessionTest):
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

    # Anon: de pagina is publiek leesbaar én indexeerbaar (open platform).
    client = make_client(None)
    resp = client.get("/nieuws")
    assert resp.status_code == 200
    assert "noindex" not in resp.text  # publiek-indexeerbaar (geen noindex)
    assert "ZICHTBAAR LIVE" in resp.text
    assert "VERBORGEN KANDIDAAT" not in resp.text  # pending nooit publiek (kritiek)
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


def _job_with_fake_session(db, monkeypatch):
    """Bekabel de curate_news-job zodat main() de rollback-geïsoleerde ``db``
    gebruikt zonder echt te committen (anders lekt/breekt de isolatie), met
    Telegram-notify uit. Geeft de job-module terug."""
    import contextlib

    from app.jobs import curate_news as job

    monkeypatch.setattr(job.settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(job, "_notify_admins", lambda *a, **k: None)

    @contextlib.contextmanager
    def fake_session():
        real_commit = db.commit
        db.commit = db.flush  # no-op commit → test-isolatie blijft intact
        try:
            yield db
        finally:
            db.commit = real_commit

    monkeypatch.setattr(job, "SessionLocal", fake_session)
    return job


def test_curate_news_job_retries_on_empty_then_persists(db, monkeypatch):
    """Regressie: het model gaf soms een lege lijst terwijl er wél nieuws was. De
    job doet één herkansing en persisteert de kandidaat van de tweede run."""
    from app.models import Post, PostKind

    job = _job_with_fake_session(db, monkeypatch)
    calls = {"n": 0}

    def fake_curate(_db, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return []  # eerste run haakt af
        return [
            news_curation_service.NewsCandidate(
                title="Herkansing-hit", url="https://retry.example/win",
                ai_take="waarom", ai_relevance=85,
            )
        ]

    monkeypatch.setattr(job.news_curation_service, "curate", fake_curate)

    created = job.main()
    assert calls["n"] == 2  # leeg → precies één herkansing
    assert created == 1
    row = db.scalar(
        select(Post).where(
            Post.kind == PostKind.nieuws, Post.url == "https://retry.example/win"
        )
    )
    assert row is not None and row.review_state == PostReviewState.pending_review


def test_curate_news_job_no_retry_when_first_run_has_items(db, monkeypatch):
    """Geen dubbele web-search-kosten: een eerste run met items retryt niet."""
    job = _job_with_fake_session(db, monkeypatch)
    calls = {"n": 0}

    def fake_curate(_db, **kw):
        calls["n"] += 1
        return [
            news_curation_service.NewsCandidate(
                title="Direct raak", url="https://direct.example/a",
                ai_take="waarom", ai_relevance=85,
            )
        ]

    monkeypatch.setattr(job.news_curation_service, "curate", fake_curate)

    created = job.main()
    assert calls["n"] == 1  # geen herkansing nodig
    assert created == 1


def test_prompt_covers_two_tracks_diversity_and_recency():
    """Regressie-guard op de bredere redactionele intentie: de curator moet twee
    sporen vullen (NL/BE + wereldwijd), thematisch spreiden en op recente items
    mikken — de fix tegen 'dun + steeds dezelfde AI-Act-story'."""
    sys = news_curation_service.SYSTEM_PROMPT.lower()
    assert "spoor 1" in sys and "spoor 2" in sys
    assert "diversiteit" in sys
    assert "1–2 weken" in sys or "1-2 weken" in sys
    # Max ~2 per thema staat expliciet als rem op de broken-record.
    assert "per thema" in sys


def test_seed_prompt_dedup_forbids_same_story(db):
    """De dedup-context verbiedt niet alleen exacte URL's maar óók een ander
    artikel over hetzelfde verhaal — de kern van de anti-herhaling."""
    post_service.create_curated_news(
        db, title="EU AI Act uitleg", url="https://a.example/aiact",
        ai_take="why", ai_relevance=80,
    )
    db.flush()
    seed = news_curation_service._seed_prompt(db).lower()
    assert "hetzelfde verhaal" in seed
    assert "beide sporen" in seed


def test_link_domain_extracts_clean_host():
    d = post_service.link_domain
    assert d("https://nl.linkedin.com/in/frankoonk") == "linkedin.com"
    assert d("https://www.oost.nl/nieuws/326166/x") == "oost.nl"
    assert d("https://www.instagram.com/frankoonk/") == "instagram.com"
    assert d("https://www.bnr.nl/podcast/cryptocast/10485656/234-b") == "bnr.nl"
    assert d("") == ""
    assert d(None) == ""
    assert d("not-a-url") == ""  # geen netloc → leeg (kaart toont niets)


def _footprint_post(s, *, member_id, url, title, role):
    from app.models import NewsRole, Post, PostKind, PostReviewState, PostSourceKind

    s.add(
        Post(
            kind=PostKind.nieuws,
            title=title,
            url=url,
            added_by_id=member_id,
            role=NewsRole(role),
            source_kind=PostSourceKind.member,
            review_state=PostReviewState.live,
        )
    )


def _member_with_profile(s, *, email, name, slug, visibility):
    from app.models import Member, Profile, Visibility

    m = Member(email=email, name=name, status=MemberStatus.approved,
               role=MemberRole.member)
    s.add(m)
    s.flush()
    s.add(Profile(member_id=m.id, slug=slug, display_name=name,
                  visibility=Visibility(visibility)))
    return m


def test_news_card_shows_origin_and_links_public_member(make_client, SessionTest):
    """Footprint-item zonder ``source`` toont nu het domein als herkomst-chip, en
    de attributie linkt naar de graaf-knoop (openbaar profiel)."""
    s = SessionTest()
    m = _member_with_profile(
        s, email="frank@example.com", name="Frank Oonk",
        slug="frank-oonk", visibility="public",
    )
    _footprint_post(
        s, member_id=m.id, url="https://www.instagram.com/frankoonk/",
        title="Frank Oonk op Instagram", role="gedeeld",
    )
    s.commit()
    s.close()

    resp = make_client(None).get("/nieuws")  # anon
    assert resp.status_code == 200
    assert "instagram.com" in resp.text  # herkomst-chip (domein uit URL)
    assert "/leden/frank-oonk" in resp.text  # attributie → profiel (graaf-knoop)


def test_footprint_news_of_private_member_hidden_from_visitor(make_client, SessionTest):
    """Nieuws van een besloten lid — een footprint-item dat het lid in de titel
    identificeert ("Wouter Dammers - Eve.law") — valt VOLLEDIG weg voor een
    bezoeker: content volgt de profiel-zichtbaarheid. Een lid ziet het wel."""
    from app.models import Member, MemberStatus

    s = SessionTest()
    m = _member_with_profile(
        s, email="wouter@example.com", name="Wouter Dammers",
        slug="wouter-dammers", visibility="members",
    )
    _footprint_post(
        s, member_id=m.id, url="https://eve.law/arbiters/wouter-dammers/",
        title="Wouter Dammers - Eve.law (arbiter)", role="gedeeld",
    )
    watcher = Member(email="kijk@example.com", name="Kijkend Lid",
                     status=MemberStatus.approved)
    s.add(watcher); s.commit()
    watcher_id = watcher.id
    s.close()

    # Bezoeker: niets van het besloten lid lekt (naam, domein-chip, noch link).
    anon = make_client(None).get("/nieuws")
    assert anon.status_code == 200
    assert "Wouter Dammers" not in anon.text
    assert "eve.law" not in anon.text
    assert "/leden/wouter-dammers" not in anon.text

    # Lid: ziet alles (leden zien elkaar volledig).
    lid = make_client(watcher_id).get("/nieuws")
    assert lid.status_code == 200
    assert "Wouter Dammers" in lid.text


def test_group_context_returns_names_with_real_rows(db):
    """Regressie: _group_context las ``t.name`` op een ``select(Tag.name)`` (al
    strings) → crashte zodra er échte tags/tools waren (lege test-DB miste 't).
    Met rijen mag het niet crashen en moet het de namen platweg teruggeven."""
    db.add_all(
        [
            Tag(name="agents", slug="agents"),
            Tag(name="evals", slug="evals"),
            Tool(name="Claude Code", slug="claude-code"),
        ]
    )
    db.flush()
    tags, tools = news_curation_service._group_context(db)
    assert "agents" in tags and "evals" in tags
    assert "Claude Code" in tools
    # En de seed-prompt bouwt zonder fout (het pad dat in prod faalde).
    assert news_curation_service._seed_prompt(db)
