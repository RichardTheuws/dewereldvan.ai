"""Route-smoke for AI-native profielbouw (F1-F2) with a fully-mocked service.

No network, no Anthropic key, no fal cost:
- ``current_member`` is overridden to control auth state (anon / pending / approved).
- ``get_db`` shares the in-memory session-scoped engine.
- The Anthropic two-step flow is patched at the *service* boundary
  (``ai_service.stream_turn`` / ``ai_service.finalize_draft``) so the routes are
  exercised end-to-end without ever touching the SDK.
- The cover backend is the ``FakeImageGenerator`` injected via ``image_generator``.

Covers: require_approved guard, message persistence + rate-limit, SSE shape,
draft persistence (never auto-publish), refusal handling, cover graceful-fail,
and publish -> 303 with conversation cleared.
"""

from __future__ import annotations

import re

import pytest
from app.models import Base
from app.services.ai_profile import DraftProfile, DraftProject, DraftRole
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests._ai_helpers import FakeImageGenerator


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture
def route_engine():
    """A DEDICATED in-memory engine for the route tests.

    These tests ``commit`` real rows through the app (no rollback isolation), so
    they must NOT share the session-scoped ``engine`` fixture — otherwise their
    committed data would leak into the rollback-isolated ``db`` fixture used by
    sibling suites. A throwaway engine per test keeps everything hermetic.
    """
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
    return sessionmaker(
        bind=route_engine, autoflush=False, autocommit=False, future=True
    )


@pytest.fixture
def seed(SessionTest):
    """Create an approved + a pending member in the throwaway route engine."""
    from app.models import Member, MemberStatus

    s = SessionTest()
    approved = Member(
        email="builder@example.com", name="Bouwer", status=MemberStatus.approved
    )
    pending = Member(
        email="pending@example.com", name="Wachtend", status=MemberStatus.pending
    )
    s.add_all([approved, pending])
    s.commit()
    ids = {"approved": approved.id, "pending": pending.id}
    s.close()
    # No teardown needed: route_engine is a throwaway DB dropped after each test.
    return ids


@pytest.fixture
def make_client(route_engine, SessionTest, fake_image_generator):
    """Factory: a TestClient whose current_member is a chosen member (or None).

    ``current_member`` is overridden to load the member from the *request-scoped*
    db session (via Depends(get_db)) so the returned instance is session-bound —
    the routes lazy-load ``member.profile`` and must not hit a DetachedInstance.
    """
    from app.db import get_db
    from app.deps import current_member, image_generator
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
            if member_id is None:
                return None
            return db.get(Member, member_id)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        app.dependency_overrides[image_generator] = lambda: fake_image_generator
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def _csrf(client: TestClient) -> str:
    """GET the build page (mints the session CSRF token) and extract it."""
    page = client.get("/profiel/ai/bouwen")
    assert page.status_code == 200
    m = re.search(r'X-CSRF-Token&#34;: &#34;([^&]+)&#34;', page.text) or re.search(
        r'name="csrf_token" value="([^"]+)"', page.text
    )
    assert m, "CSRF token not found on build page"
    return m.group(1)


# --------------------------------------------------------------------------- #
# require_approved guard                                                       #
# --------------------------------------------------------------------------- #
def test_build_page_anonymous_redirects_to_login(make_client):
    client = make_client(None)
    resp = client.get("/profiel/ai/bouwen", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_build_page_pending_member_redirects(make_client, seed):
    client = make_client(seed["pending"])
    resp = client.get("/profiel/ai/bouwen", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_build_page_approved_member_ok(make_client, seed):
    client = make_client(seed["approved"])
    resp = client.get("/profiel/ai/bouwen")
    assert resp.status_code == 200
    assert "tekst/event-stream" not in resp.text  # sanity: it's HTML


# --------------------------------------------------------------------------- #
# POST /bericht -> persist user turn (+ rate limit)                            #
# --------------------------------------------------------------------------- #
def test_post_message_persists_user_turn(make_client, seed, SessionTest):
    from app.models import AiChatTurn

    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/bericht",
        data={"message": "Ik ben maker van zorgtech."},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "sse-connect=\"/profiel/ai/stream\"" in resp.text

    s = SessionTest()
    try:
        rows = (
            s.query(AiChatTurn)
            .filter(AiChatTurn.member_id == seed["approved"], AiChatTurn.role == "user")
            .all()
        )
        assert len(rows) == 1
    finally:
        s.close()


def test_post_message_blank_is_rejected(make_client, seed):
    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/bericht", data={"message": "   "}, headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 400


def test_post_message_without_csrf_is_403(make_client, seed):
    client = make_client(seed["approved"])
    # Ensure a session/token exists, but deliberately omit the header.
    _csrf(client)
    resp = client.post("/profiel/ai/bericht", data={"message": "hoi"})
    assert resp.status_code == 403


def test_post_message_rate_limited(make_client, seed, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "rate_limit_ai_enrich_per_hour", 2)
    client = make_client(seed["approved"])
    token = _csrf(client)
    for _ in range(2):
        ok = client.post(
            "/profiel/ai/bericht",
            data={"message": "bericht"},
            headers={"X-CSRF-Token": token},
        )
        assert ok.status_code == 200
    blocked = client.post(
        "/profiel/ai/bericht",
        data={"message": "te veel"},
        headers={"X-CSRF-Token": token},
    )
    assert blocked.status_code == 429


# --------------------------------------------------------------------------- #
# SSE stream                                                                   #
# --------------------------------------------------------------------------- #
def test_stream_emits_deltas_and_done(make_client, seed, monkeypatch, SessionTest):
    """A mocked stream_turn produces delta events + a terminating done event."""
    from app.models import AiChatTurn
    from app.services import ai_profile as ai_service

    # Seed one user turn so there is conversation context to stream against.
    s = SessionTest()
    s.add(AiChatTurn(member_id=seed["approved"], role="user", content_json='"hoi"'))
    s.commit()
    s.close()

    class _Final:
        stop_reason = "end_turn"
        content = [{"type": "text", "text": "Hallo!"}]

    def _fake_stream_turn(messages, send, **kw):
        send("Hal")
        send("lo!")
        return _Final()

    monkeypatch.setattr(ai_service, "stream_turn", _fake_stream_turn)

    client = make_client(seed["approved"])
    with client.stream("GET", "/profiel/ai/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert "event: delta" in body
    assert "Hal" in body and "lo!" in body
    assert "event: done" in body


def test_stream_refusal_renders_friendly_message(make_client, seed, monkeypatch, SessionTest):
    """A refusal stop_reason yields a friendly bubble, no crash, no content[0]."""
    from app.models import AiChatTurn
    from app.services import ai_profile as ai_service

    s = SessionTest()
    s.add(AiChatTurn(member_id=seed["approved"], role="user", content_json='"x"'))
    s.commit()
    s.close()

    class _Refused:
        stop_reason = "refusal"
        content = []  # must never be indexed

    monkeypatch.setattr(
        ai_service, "stream_turn", lambda messages, send, **kw: _Refused()
    )
    client = make_client(seed["approved"])
    with client.stream("GET", "/profiel/ai/stream") as resp:
        body = "".join(resp.iter_text())
    assert resp.status_code == 200
    assert "event: done" in body
    assert "kon hier niet op ingaan" in body


# --------------------------------------------------------------------------- #
# POST /maak-draft -> persist DRAFT, never auto-publish                        #
# --------------------------------------------------------------------------- #
def test_make_draft_persists_without_changing_visibility(
    make_client, seed, monkeypatch, SessionTest
):
    from app.models import AiChatTurn, Member, Visibility
    from app.services import ai_profile as ai_service
    from app.services.profile_service import get_or_create_profile

    # Seed a user turn (finalize_draft needs conversation context).
    s = SessionTest()
    s.add(
        AiChatTurn(
            member_id=seed["approved"],
            role="user",
            content_json='"Ik ben CTO bij Acme en bouw dewereldvan.ai."',
        )
    )
    s.commit()
    s.close()

    draft = DraftProfile(
        headline="CTO & maker",
        bio="Ik bouw platforms.",
        roles=[
            DraftRole(
                label="CTO", url="https://acme", description=None, image_url=None
            )
        ],
        projects=[
            DraftProject(
                name="dewereldvan.ai",
                url="https://dwv",
                description="Platform",
                image_url=None,
            )
        ],
        seeking="medebouwers",
        tags=["python", "ai"],
    )
    monkeypatch.setattr(ai_service, "finalize_draft", lambda messages, **kw: draft)

    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post("/profiel/ai/maak-draft", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200

    s = SessionTest()
    try:
        member = s.get(Member, seed["approved"])
        profile = get_or_create_profile(s, member)
        assert profile.ai_enriched is True
        assert profile.headline == "CTO & maker"
        assert profile.bio == "Ik bouw platforms."
        assert profile.ai_source_text and "CTO bij Acme" in profile.ai_source_text
        # roles -> profile_links (affiliation); projects -> offerings; tags set.
        assert any(link.label == "CTO" for link in profile.profile_links)
        assert any(off.title == "dewereldvan.ai" for off in profile.offerings)
        assert {t.name for t in profile.tags} == {"python", "ai"}
        # CRITICAL: never auto-publish — still members-only.
        assert profile.visibility is Visibility.members
        assert profile.consented_public_at is None
    finally:
        s.close()


def test_regenerate_renamed_project_keeps_slug_and_301s(
    make_client, seed, monkeypatch, SessionTest
):
    """Een regenerate die een projecttitel wijzigt mag de slug-historie niet wissen.

    De offerings worden op positie gereconcilieerd: dezelfde rij blijft bestaan en
    ``rename_to`` legt de oude slug vast, zodat de oude ``/projecten/{slug}`` een
    301 naar de nieuwe geeft (linkwaarde-behoud) i.p.v. een 404 na clear+recreate.
    """
    from app.models import AiChatTurn, Member
    from app.services import ai_profile as ai_service
    from app.services.profile_service import get_or_create_profile

    s = SessionTest()
    s.add(
        AiChatTurn(
            member_id=seed["approved"], role="user", content_json='"Ik bouw dingen."'
        )
    )
    s.commit()
    s.close()

    def _draft(name: str) -> DraftProfile:
        return DraftProfile(
            headline="Maker",
            bio="Ik bouw.",
            roles=[],
            projects=[
                DraftProject(
                    name=name, url="https://p", description="Een project", image_url=None
                )
            ],
            seeking=None,
            tags=[],
        )

    client = make_client(seed["approved"])
    token = _csrf(client)

    # Eerste generatie: project "Oude Projectnaam".
    monkeypatch.setattr(
        ai_service, "finalize_draft", lambda messages, **kw: _draft("Oude Projectnaam")
    )
    resp = client.post("/profiel/ai/maak-draft", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200

    s = SessionTest()
    try:
        member = s.get(Member, seed["approved"])
        profile = get_or_create_profile(s, member)
        assert len(profile.offerings) == 1
        old_slug = profile.offerings[0].slug
        old_offering_id = profile.offerings[0].id
    finally:
        s.close()
    assert old_slug == "oude-projectnaam"

    # Regenerate met gewijzigde titel — zelfde positie, dus dezelfde rij + 301.
    monkeypatch.setattr(
        ai_service,
        "finalize_draft",
        lambda messages, **kw: _draft("Nieuwe Projectnaam"),
    )
    resp = client.post("/profiel/ai/maak-draft", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200

    s = SessionTest()
    try:
        member = s.get(Member, seed["approved"])
        profile = get_or_create_profile(s, member)
        # Eén project, dezelfde rij (id behouden), nieuwe slug.
        assert len(profile.offerings) == 1
        assert profile.offerings[0].id == old_offering_id
        new_slug = profile.offerings[0].slug
    finally:
        s.close()
    assert new_slug == "nieuwe-projectnaam"

    # De oude slug 301't nu naar de nieuwe (history-tabel daadwerkelijk gevuld).
    redirect = client.get(f"/projecten/{old_slug}", follow_redirects=False)
    assert redirect.status_code == 301
    assert redirect.headers["location"] == f"/projecten/{new_slug}"


def test_make_draft_without_conversation_is_rejected(make_client, seed):
    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post("/profiel/ai/maak-draft", headers={"X-CSRF-Token": token})
    assert resp.status_code == 400
    assert "Vertel eerst iets" in resp.text


def test_make_draft_refusal_shows_message_no_crash(
    make_client, seed, monkeypatch, SessionTest
):
    from app.models import AiChatTurn
    from app.services import ai_profile as ai_service

    s = SessionTest()
    s.add(AiChatTurn(member_id=seed["approved"], role="user", content_json='"hoi"'))
    s.commit()
    s.close()

    def _refuse(messages, **kw):
        raise ai_service.EnrichmentRefused()

    monkeypatch.setattr(ai_service, "finalize_draft", _refuse)
    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post("/profiel/ai/maak-draft", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200
    assert "kon niet opgesteld worden" in resp.text


# --------------------------------------------------------------------------- #
# POST /cover -> graceful fail                                                 #
# --------------------------------------------------------------------------- #
def test_cover_success_sets_url(make_client, seed, SessionTest):
    from app.models import Member
    from app.services.profile_service import get_or_create_profile

    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post("/profiel/ai/cover", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200

    s = SessionTest()
    try:
        member = s.get(Member, seed["approved"])
        profile = get_or_create_profile(s, member)
        assert profile.cover_image_url == FakeImageGenerator.URL
    finally:
        s.close()


def test_cover_failure_is_graceful(route_engine, SessionTest, seed, monkeypatch):
    """A failing image backend must not break the route; no cover URL is set."""
    from app.db import get_db
    from app.deps import current_member, image_generator
    from app.main import app
    from app.models import Member
    from app.services.profile_service import get_or_create_profile
    from fastapi import Depends
    from sqlalchemy.orm import Session

    failing = FakeImageGenerator(fail=True)

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    def _override_current_member(db: Session = Depends(get_db)):
        return db.get(Member, seed["approved"])

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[current_member] = _override_current_member
    app.dependency_overrides[image_generator] = lambda: failing
    try:
        client = TestClient(app, base_url="https://testserver")
        token = _csrf(client)
        resp = client.post("/profiel/ai/cover", headers={"X-CSRF-Token": token})
        assert resp.status_code == 200
        assert "kon nu niet gegenereerd" in resp.text
        s = SessionTest()
        try:
            member = s.get(Member, seed["approved"])
            profile = get_or_create_profile(s, member)
            assert profile.cover_image_url is None
        finally:
            s.close()
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# POST /publiceren -> 303 + turns cleared                                      #
# --------------------------------------------------------------------------- #
def test_publish_members_redirects_and_clears_turns(
    make_client, seed, SessionTest
):
    from app.models import AiChatTurn, Member
    from app.services.profile_service import get_or_create_profile

    # Seed turns to prove they are cleared on publish.
    s = SessionTest()
    s.add(AiChatTurn(member_id=seed["approved"], role="user", content_json='"hoi"'))
    member = s.get(Member, seed["approved"])
    profile = get_or_create_profile(s, member)
    slug = profile.slug
    s.commit()
    s.close()

    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/publiceren",
        data={"visibility": "members"},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/leden/{slug}"

    s = SessionTest()
    try:
        remaining = (
            s.query(AiChatTurn)
            .filter(AiChatTurn.member_id == seed["approved"])
            .count()
        )
        assert remaining == 0
    finally:
        s.close()


def test_publish_public_without_consent_is_rejected(make_client, seed, SessionTest):
    from app.models import Member, Visibility
    from app.services.profile_service import get_or_create_profile

    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/publiceren",
        data={"visibility": "public"},  # no consent
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "toestemming" in resp.text

    s = SessionTest()
    try:
        member = s.get(Member, seed["approved"])
        profile = get_or_create_profile(s, member)
        assert profile.visibility is Visibility.members  # not flipped
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Security: streamed deltas are HTML-escaped (no live-stream DOM-XSS)          #
# --------------------------------------------------------------------------- #
def test_stream_escapes_delta_markup(make_client, seed, monkeypatch, SessionTest):
    """Model output containing markup is escaped before it hits the delta sink."""
    from app.models import AiChatTurn
    from app.services import ai_profile as ai_service

    s = SessionTest()
    s.add(AiChatTurn(member_id=seed["approved"], role="user", content_json='"hoi"'))
    s.commit()
    s.close()

    class _Final:
        stop_reason = "end_turn"
        content = [{"type": "text", "text": "ok"}]

    def _fake_stream_turn(messages, send, **kw):
        send("<img src=x onerror=alert(1)>")
        return _Final()

    monkeypatch.setattr(ai_service, "stream_turn", _fake_stream_turn)

    client = make_client(seed["approved"])
    with client.stream("GET", "/profiel/ai/stream") as resp:
        body = "".join(resp.iter_text())
    # The raw tag must NOT appear in a delta event; its escaped form must.
    assert "<img src=x onerror=alert(1)>" not in body
    assert "&lt;img src=x onerror=alert(1)&gt;" in body


# --------------------------------------------------------------------------- #
# AVG: 'Opnieuw beginnen' erases the stored raw member input + AI cover        #
# --------------------------------------------------------------------------- #
def test_restart_erases_ai_source_text_and_cover(make_client, seed, SessionTest):
    from app.models import Member
    from app.services.profile_service import get_or_create_profile

    s = SessionTest()
    member = s.get(Member, seed["approved"])
    profile = get_or_create_profile(s, member)
    profile.ai_enriched = True
    profile.ai_source_text = "Persoonlijke ruwe invoer van het lid."
    profile.cover_image_url = "https://img.test/cover.png"
    s.commit()
    s.close()

    client = make_client(seed["approved"])
    token = _csrf(client)
    resp = client.post(
        "/profiel/ai/opnieuw",
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    s = SessionTest()
    try:
        member = s.get(Member, seed["approved"])
        profile = get_or_create_profile(s, member)
        assert profile.ai_enriched is False
        assert profile.ai_source_text is None
        assert profile.cover_image_url is None
    finally:
        s.close()
