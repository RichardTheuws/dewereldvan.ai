"""Tests for the feedback layer (E1): opslag, rate-limit, admin-poort, verbergen.

No network, no Anthropic key:
- ``current_member`` is overridden (anon / member / admin) via a session-bound
  loader, so the public/admin guards see the exact auth state under test.
- The Claude-summary path is patched at the service boundary
  (``feedback_service._summarize``) so the enrichment never touches the SDK.

A dedicated throwaway engine per test keeps the committed rows out of the
rollback-isolated ``db`` fixture used by sibling suites.
"""

from __future__ import annotations

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
    """One approved member + one admin member in the throwaway engine."""
    from app.models import Member, MemberRole, MemberStatus

    s = SessionTest()
    member = Member(
        email="lid@example.com", name="Test Lid", status=MemberStatus.approved
    )
    admin = Member(
        email="admin@example.com",
        name="Beheerder",
        status=MemberStatus.approved,
        role=MemberRole.admin,
    )
    s.add_all([member, admin])
    s.commit()
    ids = {"member": member.id, "admin": admin.id}
    s.close()
    return ids


@pytest.fixture
def make_client(route_engine, SessionTest):
    """Factory: a TestClient whose current_member is a chosen member (or None)."""
    from app.db import get_db
    from app.deps import current_member, email_sender
    from app.main import app
    from app.models import Member

    from tests.conftest import FakeEmailSender

    fake_sender = FakeEmailSender()

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
        app.dependency_overrides[email_sender] = lambda: fake_sender
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def _count_feedback(SessionTest) -> int:
    from app.models import Feedback

    s = SessionTest()
    try:
        return s.query(Feedback).count()
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Opslag                                                                       #
# --------------------------------------------------------------------------- #
def test_submit_without_csrf_is_403(make_client, seed):
    client = make_client(seed["member"])
    csrf_token(client)  # mint a session, but omit the header/field on the POST
    resp = client.post("/feedback", data={"body": "Iets"})
    assert resp.status_code == 403


def test_submit_as_member_persists_with_page_path(make_client, seed, SessionTest, monkeypatch):
    from app.models import Feedback
    from app.services import feedback_service

    # Keep enrichment out of the SDK entirely.
    monkeypatch.setattr(feedback_service, "_summarize", lambda body, page_path: None)

    client = make_client(seed["member"])
    token = csrf_token(client)
    resp = client.post(
        "/feedback",
        data={
            "body": "Wat een mooie ledenpagina.",
            "kind": "lof",
            "page_path": "https://testserver/leden/iemand?x=1",
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        rows = s.query(Feedback).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.member_id == seed["member"]
        assert row.body == "Wat een mooie ledenpagina."
        # The route reduces the supplied page_path to the path only (no host/query).
        assert row.page_path == "/leden/iemand"
        assert row.kind == "lof"
    finally:
        s.close()


def test_submit_anonymous_persists_with_null_member(make_client, SessionTest, monkeypatch):
    from app.models import Feedback
    from app.services import feedback_service

    monkeypatch.setattr(feedback_service, "_summarize", lambda body, page_path: None)

    client = make_client(None)
    token = csrf_token(client)
    resp = client.post(
        "/feedback",
        data={"body": "Anonieme gedachte."},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        rows = s.query(Feedback).all()
        assert len(rows) == 1
        assert rows[0].member_id is None
    finally:
        s.close()


def test_blank_body_is_rejected(make_client, seed, SessionTest):
    client = make_client(seed["member"])
    token = csrf_token(client)
    resp = client.post(
        "/feedback", data={"body": "   "}, headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 400
    assert _count_feedback(SessionTest) == 0


# --------------------------------------------------------------------------- #
# Rate-limit (per ingelogd lid)                                               #
# --------------------------------------------------------------------------- #
def test_rate_limit_blocks_excess_for_member(make_client, seed, SessionTest, monkeypatch):
    from app.config import settings
    from app.services import feedback_service

    monkeypatch.setattr(settings, "rate_limit_feedback_per_hour", 2)
    monkeypatch.setattr(feedback_service, "_summarize", lambda body, page_path: None)

    client = make_client(seed["member"])
    token = csrf_token(client)
    for _ in range(2):
        ok = client.post(
            "/feedback", data={"body": "telt mee"}, headers={"X-CSRF-Token": token}
        )
        assert ok.status_code == 200
    blocked = client.post(
        "/feedback", data={"body": "een te veel"}, headers={"X-CSRF-Token": token}
    )
    assert blocked.status_code == 429
    # The blocked submit left no extra row behind.
    assert _count_feedback(SessionTest) == 2


# --------------------------------------------------------------------------- #
# Claude-samenvatting (best-effort, niet-blokkerend)                          #
# --------------------------------------------------------------------------- #
def test_summary_filled_when_claude_answers(make_client, seed, SessionTest, monkeypatch):
    from app.config import settings
    from app.models import Feedback
    from app.services import feedback_service

    monkeypatch.setattr(settings, "ai_enrich_enabled", True)
    monkeypatch.setattr(
        feedback_service, "_summarize", lambda body, page_path: "Lid prijst de pagina. [lof]"
    )

    client = make_client(seed["member"])
    token = csrf_token(client)
    resp = client.post(
        "/feedback", data={"body": "Top pagina!"}, headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        row = s.query(Feedback).one()
        assert row.ai_summary == "Lid prijst de pagina. [lof]"
    finally:
        s.close()


def test_summary_failure_does_not_block_storage(make_client, seed, SessionTest, monkeypatch):
    """If Claude raises, the feedback is still stored with ai_summary=None."""
    from app.config import settings
    from app.models import Feedback

    monkeypatch.setattr(settings, "ai_enrich_enabled", True)

    # Drive the *real* _summarize through a raising fake Anthropic client so the
    # try/except best-effort guard is exercised, not bypassed.
    import anthropic

    class _Boom:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kw):
                raise RuntimeError("geen API-key / netwerk")

    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: _Boom())

    client = make_client(seed["member"])
    token = csrf_token(client)
    resp = client.post(
        "/feedback", data={"body": "Werkt het wel?"}, headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        row = s.query(Feedback).one()
        assert row.ai_summary is None  # enrichment failed -> NULL, storage OK
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Admin-poort + verbergen                                                      #
# --------------------------------------------------------------------------- #
def test_admin_overview_requires_admin(make_client, seed):
    member_client = make_client(seed["member"])
    assert member_client.get("/admin/feedback").status_code == 403

    anon_client = make_client(None)
    resp = anon_client.get("/admin/feedback", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_admin_overview_lists_items(make_client, seed, SessionTest, monkeypatch):
    from app.services import feedback_service

    monkeypatch.setattr(feedback_service, "_summarize", lambda body, page_path: None)

    # Seed one feedback row via the member submit path.
    member_client = make_client(seed["member"])
    token = csrf_token(member_client)
    member_client.post(
        "/feedback",
        data={"body": "Zichtbaar in admin."},
        headers={"X-CSRF-Token": token},
    )

    admin_client = make_client(seed["admin"])
    resp = admin_client.get("/admin/feedback")
    assert resp.status_code == 200
    assert "Zichtbaar in admin." in resp.text


def test_admin_hide_toggles_hidden_and_audits(make_client, seed, SessionTest, monkeypatch):
    from app.models import AuditAction, AuditLog, Feedback
    from app.services import feedback_service

    monkeypatch.setattr(feedback_service, "_summarize", lambda body, page_path: None)

    member_client = make_client(seed["member"])
    token = csrf_token(member_client)
    member_client.post(
        "/feedback", data={"body": "Verberg mij."}, headers={"X-CSRF-Token": token}
    )

    s = SessionTest()
    fb_id = s.query(Feedback).one().id
    s.close()

    admin_client = make_client(seed["admin"])
    admin_token = csrf_token(admin_client)
    resp = admin_client.post(
        f"/admin/feedback/{fb_id}/verberg",
        headers={"X-CSRF-Token": admin_token},
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        row = s.get(Feedback, fb_id)
        assert row.hidden is True
        audits = (
            s.query(AuditLog)
            .filter(AuditLog.action == AuditAction.feedback_hidden)
            .all()
        )
        assert len(audits) == 1
        assert audits[0].actor_member_id == seed["admin"]
    finally:
        s.close()
