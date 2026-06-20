"""Tests voor de footprint-engine + de live-discovery (Fase 1a).

Geen netwerk, geen Anthropic-key:
- De service-tests voeren een in-memory fake client in die ÉÉN ``record_findings``-
  tool-use teruggeeft (gespiegeld van de fake uit ``test_concierge.py``).
- De route-tests overrijden ``current_member`` + ``get_db`` (gespiegeld van
  ``test_ai_profile_routes.py``) en patchen ``footprint_service.discover``.

Dekt: seed/ankers, sanitering (grounding op echte URL, enum-klem, confidence-
clamp), de pause_turn-loop, gating-off → lege/done, en de stream-route-vorm.
"""

from __future__ import annotations

import json

import pytest
from app.models import Base
from app.services import footprint_service
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# --------------------------------------------------------------------------- #
# Fake Anthropic met een record_findings-tool-use (streaming)                 #
# --------------------------------------------------------------------------- #


class _Block:
    """Minimaal content-blok met dict-achtige .type/.name/.input/.id velden."""

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
        step = self._owner.script[self._owner.call_idx]
        return iter(step.get("deltas", []))

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


def _findings_block(findings):
    return _Block(type="tool_use", name="record_findings", id="t1",
                  input={"findings": findings})


# --------------------------------------------------------------------------- #
# Service: discover happy path + grounding/sanitering                          #
# --------------------------------------------------------------------------- #


def _drain(profile, fake):
    """Draai discover en verzamel de events als (event, data)-lijst."""
    events: list[tuple[str, str]] = []
    findings = footprint_service.discover(
        profile, lambda e, d: events.append((e, d)), client=fake
    )
    return findings, events


def test_discover_streams_grounded_findings(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Sanne Maker")
    profile = make_profile(member, display_name="Sanne Maker")

    fake = FakeAnthropic([
        {
            "stop_reason": "end_turn",
            "content": [_findings_block([
                {"title": "Zorg-AI project", "url": "https://sanne.example/project",
                 "type": "project", "confidence": 92, "why": "Eigen domein."},
                {"title": "Interview in NRC", "url": "https://nrc.example/sanne",
                 "type": "media", "confidence": 71, "why": "Geïnterviewd."},
            ])],
        },
    ])

    findings, events = _drain(profile, fake)

    assert len(findings) == 2
    assert findings[0].type == "project" and findings[0].confidence == 92
    types = [e for e, _ in events]
    assert "search" in types
    assert types.count("candidate") == 2
    assert types[-1] == "done"
    # Candidate-events dragen de echte data als JSON.
    cand = [json.loads(d) for e, d in events if e == "candidate"]
    assert cand[0]["url"] == "https://sanne.example/project"
    assert cand[1]["type"] == "media"


def test_discover_sanitizes_enum_confidence_and_url(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Jan")
    profile = make_profile(member, display_name="Jan")

    fake = FakeAnthropic([
        {
            "stop_reason": "end_turn",
            "content": [_findings_block([
                # onbekend type -> "other"; confidence > 100 -> 100
                {"title": "Talk", "url": "https://x.example/talk",
                 "type": "PODCAST", "confidence": 250, "why": "x"},
                # geen URL -> gedropt (grounding-poort)
                {"title": "Geen link", "url": "", "type": "blog",
                 "confidence": 50, "why": "y"},
                # javascript: -> safe_url leegt -> gedropt
                {"title": "XSS", "url": "javascript:alert(1)", "type": "social",
                 "confidence": 40, "why": "z"},
                # negatieve confidence -> 0; geen title -> gedropt
                {"title": "", "url": "https://x.example/a", "type": "blog",
                 "confidence": -5, "why": "q"},
                {"title": "Blogpost", "url": "https://x.example/blog",
                 "type": "blog", "confidence": -5, "why": "q"},
            ])],
        },
    ])

    findings, _ = _drain(profile, fake)

    assert [f.title for f in findings] == ["Talk", "Blogpost"]
    assert findings[0].type == "other"  # onbekend -> other
    assert findings[0].confidence == 100  # geklemd
    assert findings[1].confidence == 0  # geklemd


def test_discover_pause_turn_loop(db, make_member, make_profile, monkeypatch):
    """Een pause_turn-stap wordt afgehandeld (content terug, opnieuw streamen)."""
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Eva")
    profile = make_profile(member, display_name="Eva")

    fake = FakeAnthropic([
        {  # ronde 1: server-tools draaien -> pause_turn
            "stop_reason": "pause_turn",
            "content": [_Block(type="server_tool_use", name="web_search", id="s1",
                               input={"query": "Eva"})],
        },
        {  # ronde 2: levert de findings
            "stop_reason": "end_turn",
            "content": [_findings_block([
                {"title": "Eva's site", "url": "https://eva.example",
                 "type": "project", "confidence": 80, "why": "eigen site"},
            ])],
        },
    ])

    findings, events = _drain(profile, fake)

    assert len(findings) == 1
    assert fake.call_idx == 2  # twee stream-calls (pause-loop)
    assert ("done", "Ik vond 1 mogelijke vermeldingen.") in events


def test_discover_refusal_returns_empty(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Refused")
    profile = make_profile(member, display_name="Refused")
    fake = FakeAnthropic([{"stop_reason": "refusal", "content": []}])

    findings, events = _drain(profile, fake)

    assert findings == []
    assert events[-1][0] == "done"


def test_discover_gated_off_is_done_no_call(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", False)
    member = make_member(name="Off")
    profile = make_profile(member, display_name="Off")
    # client zou NOOIT geraakt mogen worden; geef een bom mee.
    fake = FakeAnthropic([])

    findings, events = _drain(profile, fake)

    assert findings == []
    assert events == [("done", "AI-ontdekking staat momenteel uit.")]


def test_discover_no_findings_is_honest(db, make_member, make_profile, monkeypatch):
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Niemand")
    profile = make_profile(member, display_name="Niemand")
    fake = FakeAnthropic([{"stop_reason": "end_turn",
                           "content": [_findings_block([])]}])

    findings, events = _drain(profile, fake)

    assert findings == []
    assert events[-1] == ("done", "Ik kon online niets met zekerheid aan jou koppelen.")


def test_seed_uses_name_and_anchors(db, make_member, make_profile, make_offering):
    from app.models import ProfileLink
    from app.models.base import ProfileLinkKind

    member = make_member(name="Met Ankers")
    profile = make_profile(member, display_name="Met Ankers")
    profile.profile_links.append(
        ProfileLink(label="Site", url="https://anker.example",
                    kind=ProfileLinkKind.affiliation, position=0)
    )
    make_offering(profile, title="Project", url="https://project.example")
    db.flush()

    name, anchors = footprint_service._seed(profile)
    assert name == "Met Ankers"
    assert "https://anker.example" in anchors
    assert "https://project.example" in anchors


def test_sdk_contract_no_forbidden_params(db, make_member, make_profile, monkeypatch):
    """Geen temperature/top_p/top_k/budget_tokens; thinking=adaptive; webtools."""
    monkeypatch.setattr(footprint_service.settings, "ai_enrich_enabled", True)
    member = make_member(name="Contract")
    profile = make_profile(member, display_name="Contract")
    fake = FakeAnthropic([{"stop_reason": "end_turn",
                           "content": [_findings_block([])]}])

    _drain(profile, fake)

    kw = fake.stream_kwargs[0]
    for forbidden in ("temperature", "top_p", "top_k", "budget_tokens"):
        assert forbidden not in kw
    assert kw["thinking"] == {"type": "adaptive"}
    tool_types = {t.get("type") for t in kw["tools"]}
    assert "web_search_20260209" in tool_types
    assert "web_fetch_20260209" in tool_types
    assert any(t.get("name") == "record_findings" for t in kw["tools"])


# --------------------------------------------------------------------------- #
# Route: host renders + stream emits events/done (mocked service)             #
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
    m = Member(email="ontdek@example.com", name="Ontdekker", status=MemberStatus.approved)
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

    page = client.get("/profiel/ai/bouwen")
    assert page.status_code == 200
    m = re.search(r'X-CSRF-Token&#34;: &#34;([^&]+)&#34;', page.text) or re.search(
        r'name="csrf_token" value="([^"]+)"', page.text
    )
    assert m, "CSRF token not found"
    return m.group(1)


def test_start_renders_discovery_host(make_client, approved_id):
    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post("/profiel/ai/ontdek", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200
    assert "/profiel/ai/ontdek/stream" in resp.text
    assert "data-ontdek-host" in resp.text


def test_stream_anonymous_blocked(make_client):
    """Self-only: een anonieme bezoeker mag de stream niet openen (GET, require_member)."""
    client = make_client(None)
    resp = client.get("/profiel/ai/ontdek/stream", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_stream_emits_candidates_and_done(make_client, approved_id, monkeypatch):
    from app.services import footprint_service as fs

    def _fake_discover(profile, send_event, *, client=None):
        send_event("search", "Ik zoek je op het web…")
        send_event("candidate", json.dumps({
            "title": "Mijn project", "url": "https://x.example",
            "type": "project", "confidence": 90, "why": "eigen domein"}))
        send_event("done", "Ik vond 1 mogelijke vermeldingen.")
        return []

    monkeypatch.setattr(fs, "discover", _fake_discover)

    client = make_client(approved_id)
    with client.stream("GET", "/profiel/ai/ontdek/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())

    assert "event: search" in body
    assert "event: candidate" in body
    assert "Mijn project" in body
    assert "field--materializing" in body  # de kaart vliegt binnen
    assert "event: done" in body


def test_koppel_project_renders_offering_draft(make_client, approved_id):
    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/ontdek/koppel",
        data={"title": "Mijn project", "url": "https://x.example", "type": "project"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert 'hx-post="/profiel/ai/offering"' in resp.text
    assert "https://x.example" in resp.text


def test_koppel_media_renders_news_draft(make_client, approved_id):
    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/ontdek/koppel",
        data={"title": "Interview", "url": "https://nrc.example", "type": "media"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert 'hx-post="/nieuws"' in resp.text


def test_koppel_rejects_unsafe_url(make_client, approved_id):
    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/ontdek/koppel",
        data={"title": "x", "url": "javascript:alert(1)", "type": "project"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Fase 1b — crystalliseer/bevestig-laag (service)                              #
# --------------------------------------------------------------------------- #


def test_is_high_confidence_threshold():
    assert footprint_service.is_high_confidence(footprint_service.HIGH_CONFIDENCE)
    assert footprint_service.is_high_confidence(100)
    assert not footprint_service.is_high_confidence(footprint_service.HIGH_CONFIDENCE - 1)
    assert not footprint_service.is_high_confidence(None)
    assert not footprint_service.is_high_confidence("hoog")


def test_crystallize_project_creates_offering(db, make_member, make_profile):
    from app.models import Offering

    member = make_member(name="Maker")
    profile = make_profile(member, display_name="Maker")

    res = footprint_service.crystallize(
        db, profile, member, title="Mijn project", url="https://x.example", ftype="project"
    )

    assert res.kind == "offering"
    off = db.get(Offering, res.id)
    assert off is not None
    assert off.url == "https://x.example"
    assert off.profile_id == profile.id
    assert off.slug  # ensure_slug liep


def test_crystallize_media_creates_news_with_role(db, make_member, make_profile):
    from app.models import Post, PostKind
    from app.models.base import NewsRole

    member = make_member(name="Spreker")
    profile = make_profile(member, display_name="Spreker")

    res = footprint_service.crystallize(
        db, profile, member, title="Interview", url="https://nrc.example", ftype="media"
    )

    assert res.kind == "news"
    post = db.get(Post, res.id)
    assert post.kind == PostKind.nieuws
    assert post.role == NewsRole.vermeld
    assert post.added_by_id == member.id
    assert post.url == "https://nrc.example"


def test_crystallize_blog_role_geschreven(db, make_member, make_profile):
    from app.models import Post
    from app.models.base import NewsRole

    member = make_member(name="Blogger")
    profile = make_profile(member, display_name="Blogger")
    res = footprint_service.crystallize(
        db, profile, member, title="Mijn post", url="https://b.example", ftype="blog"
    )
    assert db.get(Post, res.id).role == NewsRole.geschreven


def test_crystallize_unknown_type_falls_back_to_news(db, make_member, make_profile):
    from app.models import Post
    from app.models.base import NewsRole

    member = make_member(name="Onbekend")
    profile = make_profile(member, display_name="Onbekend")
    res = footprint_service.crystallize(
        db, profile, member, title="Iets", url="https://o.example", ftype="PODCAST"
    )
    assert res.kind == "news"
    assert db.get(Post, res.id).role == NewsRole.gedeeld  # default-rol


def test_undo_offering_removes_it(db, make_member, make_profile):
    from app.models import Offering

    member = make_member(name="Maker")
    profile = make_profile(member, display_name="Maker")
    res = footprint_service.crystallize(
        db, profile, member, title="Project", url="https://x.example", ftype="project"
    )
    assert db.get(Offering, res.id) is not None

    ok = footprint_service.undo_crystallize(
        db, profile, member, kind="offering", entity_id=res.id
    )
    assert ok is True
    assert db.get(Offering, res.id) is None


def test_undo_news_requires_ownership(db, make_member, make_profile):
    from app.models import Post

    owner = make_member(name="Eigenaar", email="owner@example.com")
    owner_profile = make_profile(owner, display_name="Eigenaar")
    res = footprint_service.crystallize(
        db, owner_profile, owner, title="Artikel", url="https://n.example", ftype="media"
    )

    # Een ánder lid mag deze nieuws-Post niet ongedaan maken (self-only).
    intruder = make_member(name="Indringer", email="intruder@example.com")
    intruder_profile = make_profile(intruder, display_name="Indringer")
    ok = footprint_service.undo_crystallize(
        db, intruder_profile, intruder, kind="news", entity_id=res.id
    )
    assert ok is False
    assert db.get(Post, res.id) is not None  # blijft staan

    # De eigenaar mag wél.
    assert footprint_service.undo_crystallize(
        db, owner_profile, owner, kind="news", entity_id=res.id
    )
    assert db.get(Post, res.id) is None


def test_undo_offering_requires_ownership(db, make_member, make_profile):
    from app.models import Offering

    owner = make_member(name="Eigenaar", email="owner2@example.com")
    owner_profile = make_profile(owner, display_name="Eigenaar")
    res = footprint_service.crystallize(
        db, owner_profile, owner, title="Project", url="https://x.example", ftype="project"
    )
    intruder = make_member(name="Indringer", email="intruder2@example.com")
    intruder_profile = make_profile(intruder, display_name="Indringer")
    ok = footprint_service.undo_crystallize(
        db, intruder_profile, intruder, kind="offering", entity_id=res.id
    )
    assert ok is False
    assert db.get(Offering, res.id) is not None


# --------------------------------------------------------------------------- #
# Fase 1b — crystalliseer/bevestig-laag (routes + kaart-markup)               #
# --------------------------------------------------------------------------- #


def test_stream_high_confidence_card_is_auto(make_client, approved_id, monkeypatch):
    from app.services import footprint_service as fs

    def _fake_discover(profile, send_event, *, client=None):
        send_event("candidate", json.dumps({
            "title": "Zeker project", "url": "https://x.example",
            "type": "project", "confidence": 96, "why": "eigen domein"}))
        send_event("done", "klaar")
        return []

    monkeypatch.setattr(fs, "discover", _fake_discover)
    client = make_client(approved_id)
    with client.stream("GET", "/profiel/ai/ontdek/stream") as resp:
        body = "".join(resp.iter_text())

    assert "ontdek-card--auto" in body
    assert 'hx-trigger="load' in body
    assert "/profiel/ai/ontdek/crystalliseer" in body
    assert "Ik koppel dit aan je profiel" in body


def test_stream_low_confidence_card_is_confirm_row(make_client, approved_id, monkeypatch):
    from app.services import footprint_service as fs

    def _fake_discover(profile, send_event, *, client=None):
        send_event("candidate", json.dumps({
            "title": "Misschien jij", "url": "https://maybe.example",
            "type": "media", "confidence": 55, "why": "naamgenoot?"}))
        send_event("done", "klaar")
        return []

    monkeypatch.setattr(fs, "discover", _fake_discover)
    client = make_client(approved_id)
    with client.stream("GET", "/profiel/ai/ontdek/stream") as resp:
        body = "".join(resp.iter_text())

    assert "ontdek-card--auto" not in body
    assert "Klopt dit?" in body
    assert "✓ Koppelen" in body
    assert "hx-trigger=\"load" not in body


def test_crystalliseer_project_persists_and_renders_undo(
    make_client, approved_id, monkeypatch
):
    from app.services import project_enrich_service

    triggered: list[int] = []
    monkeypatch.setattr(
        project_enrich_service, "trigger_async", lambda oid: triggered.append(oid)
    )

    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/ontdek/crystalliseer",
        data={"title": "Mijn project", "url": "https://x.example",
              "type": "project", "confidence": 95},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "ontdek-card--done" in resp.text
    assert 'hx-post="/profiel/ai/ontdek/ongedaan"' in resp.text
    assert "staat nu op je profiel" in resp.text
    assert triggered  # project-enrich getriggerd


def test_crystalliseer_news_does_not_trigger_enrich(make_client, approved_id, monkeypatch):
    from app.services import project_enrich_service

    triggered: list[int] = []
    monkeypatch.setattr(
        project_enrich_service, "trigger_async", lambda oid: triggered.append(oid)
    )
    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/ontdek/crystalliseer",
        data={"title": "Interview", "url": "https://nrc.example",
              "type": "media", "confidence": 95},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "ontdek-card--done" in resp.text
    assert triggered == []  # nieuws → geen project-enrich


def test_crystalliseer_rejects_unsafe_url(make_client, approved_id):
    client = make_client(approved_id)
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/ontdek/crystalliseer",
        data={"title": "x", "url": "javascript:alert(1)", "type": "project"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400


def test_ongedaan_removes_and_offers_relink(make_client, approved_id, monkeypatch):
    from app.services import project_enrich_service

    monkeypatch.setattr(project_enrich_service, "trigger_async", lambda oid: None)
    client = make_client(approved_id)
    token = _csrf(client)
    # Eerst koppelen om een echte id te krijgen.
    made = client.post(
        "/profiel/ai/ontdek/crystalliseer",
        data={"title": "Mijn project", "url": "https://x.example",
              "type": "project", "confidence": 95},
        headers={"X-CSRF-Token": token},
    )
    import re

    m = re.search(r'name="id" value="(\d+)"', made.text)
    assert m
    oid = m.group(1)

    resp = client.post(
        "/profiel/ai/ontdek/ongedaan",
        data={"kind": "offering", "id": oid, "title": "Mijn project",
              "url": "https://x.example", "type": "project"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "Ongedaan gemaakt" in resp.text
    assert "Toch koppelen" in resp.text
    assert 'hx-post="/profiel/ai/ontdek/crystalliseer"' in resp.text


def test_crystalliseer_anonymous_blocked(make_client):
    client = make_client(None)
    resp = client.post(
        "/profiel/ai/ontdek/crystalliseer",
        data={"title": "x", "url": "https://x.example", "type": "project"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303, 403)
