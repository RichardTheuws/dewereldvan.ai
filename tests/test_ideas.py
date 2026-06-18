"""Tests for the ideeenbus (E2): indienen + rate-limit + stem-UNIEKheid + admin.

The headline guarantee here is stem-uniqueness: a member voting twice on the
same idea must yield exactly ONE IdeaVote row, count == 1, and the duplicate
POST must NOT raise a 500 (the IntegrityError is caught and treated as "already
voted") — proven both at the service layer and end-to-end through the route.

No network: ``current_member`` is overridden; admin/promote paths exercise the
real DB writes. A throwaway engine per test keeps rows hermetic.
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
    """approved member, a second member, an admin, and a pending member."""
    from app.models import Member, MemberRole, MemberStatus

    s = SessionTest()
    member = Member(email="a@example.com", name="Lid A", status=MemberStatus.approved)
    member2 = Member(email="b@example.com", name="Lid B", status=MemberStatus.approved)
    admin = Member(
        email="admin@example.com",
        name="Beheerder",
        status=MemberStatus.approved,
        role=MemberRole.admin,
    )
    pending = Member(email="p@example.com", name="Wacht", status=MemberStatus.pending)
    s.add_all([member, member2, admin, pending])
    s.commit()
    ids = {
        "member": member.id,
        "member2": member2.id,
        "admin": admin.id,
        "pending": pending.id,
    }
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


def _new_idea(SessionTest, member_id: int, *, title="Een idee", body="beschrijving") -> int:
    from app.models import Idea, IdeaStatus

    s = SessionTest()
    try:
        idea = Idea(member_id=member_id, title=title, body=body, status=IdeaStatus.open)
        s.add(idea)
        s.commit()
        return idea.id
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Auth-poort + lege staat                                                      #
# --------------------------------------------------------------------------- #
def test_index_anonymous_redirects_to_login(make_client):
    client = make_client(None)
    resp = client.get("/ideeen", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_index_pending_redirects_to_login(make_client, seed):
    client = make_client(seed["pending"])
    resp = client.get("/ideeen", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_index_approved_empty_state_ok(make_client, seed):
    client = make_client(seed["member"])
    resp = client.get("/ideeen")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# Indienen + rate-limit                                                        #
# --------------------------------------------------------------------------- #
def test_submit_persists_idea(make_client, seed, SessionTest):
    from app.models import Idea

    client = make_client(seed["member"])
    token = csrf_token(client, "/ideeen")
    resp = client.post(
        "/ideeen",
        data={"title": "Donkere modus", "body": "Maak alles nog kosmischer."},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        rows = s.query(Idea).all()
        assert len(rows) == 1
        assert rows[0].title == "Donkere modus"
        assert rows[0].member_id == seed["member"]
    finally:
        s.close()


def test_submit_blank_is_rejected(make_client, seed, SessionTest):
    from app.models import Idea

    client = make_client(seed["member"])
    token = csrf_token(client, "/ideeen")
    resp = client.post(
        "/ideeen", data={"title": "", "body": ""}, headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 400
    s = SessionTest()
    try:
        assert s.query(Idea).count() == 0
    finally:
        s.close()


def test_submit_rate_limited(make_client, seed, SessionTest, monkeypatch):
    from app.config import settings
    from app.models import Idea

    monkeypatch.setattr(settings, "rate_limit_idea_per_hour", 2)
    client = make_client(seed["member"])
    token = csrf_token(client, "/ideeen")
    for i in range(2):
        ok = client.post(
            "/ideeen",
            data={"title": f"Idee {i}", "body": "iets"},
            headers={"X-CSRF-Token": token},
        )
        assert ok.status_code == 200
    blocked = client.post(
        "/ideeen",
        data={"title": "Te veel", "body": "iets"},
        headers={"X-CSRF-Token": token},
    )
    assert blocked.status_code == 429
    s = SessionTest()
    try:
        assert s.query(Idea).count() == 2
    finally:
        s.close()


def test_submit_without_csrf_is_403(make_client, seed):
    client = make_client(seed["member"])
    csrf_token(client, "/ideeen")
    resp = client.post("/ideeen", data={"title": "x", "body": "y"})
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# Stem-UNIEKheid (kern) — service-laag                                        #
# --------------------------------------------------------------------------- #
def test_service_double_vote_is_idempotent(db, make_member, make_idea):
    """vote() twice for the same member -> 1 row, count 1, no IntegrityError up."""
    from app.models import IdeaVote
    from app.services import idea_service

    member = make_member(email="voter@example.com")
    idea = make_idea(member, title="Stem-test")

    r1 = idea_service.vote(db, idea, member)
    assert r1.created is True
    assert r1.count == 1

    r2 = idea_service.vote(db, idea, member)
    assert r2.created is False  # already voted, idempotent
    assert r2.count == 1  # no double count

    assert db.query(IdeaVote).filter(IdeaVote.idea_id == idea.id).count() == 1


def test_service_two_members_two_votes(db, make_member, make_idea):
    from app.services import idea_service

    author = make_member(email="author@example.com")
    voter1 = make_member(email="v1@example.com")
    voter2 = make_member(email="v2@example.com")
    idea = make_idea(author, title="Twee stemmen")

    idea_service.vote(db, idea, voter1)
    result = idea_service.vote(db, idea, voter2)
    assert result.count == 2


# --------------------------------------------------------------------------- #
# Stem-UNIEKheid (kern) — route-laag, end-to-end                              #
# --------------------------------------------------------------------------- #
def test_route_double_vote_no_500_single_row(make_client, seed, SessionTest):
    from app.models import IdeaVote

    idea_id = _new_idea(SessionTest, seed["member"], title="Route-stem")

    client = make_client(seed["member"])
    token = csrf_token(client, "/ideeen")

    first = client.post(f"/ideeen/{idea_id}/stem", headers={"X-CSRF-Token": token})
    assert first.status_code == 200

    # Second vote by the same member: must be a clean 200 (idempotent), not 500.
    second = client.post(f"/ideeen/{idea_id}/stem", headers={"X-CSRF-Token": token})
    assert second.status_code == 200

    s = SessionTest()
    try:
        votes = s.query(IdeaVote).filter(IdeaVote.idea_id == idea_id).all()
        assert len(votes) == 1
    finally:
        s.close()


def test_route_vote_on_missing_idea_is_404(make_client, seed):
    client = make_client(seed["member"])
    token = csrf_token(client, "/ideeen")
    resp = client.post("/ideeen/999999/stem", headers={"X-CSRF-Token": token})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Admin: verbergen + status + poort                                           #
# --------------------------------------------------------------------------- #
def test_admin_routes_require_admin(make_client, seed, SessionTest):
    idea_id = _new_idea(SessionTest, seed["member"])
    client = make_client(seed["member"])  # not an admin
    token = csrf_token(client, "/ideeen")
    for path in (
        f"/admin/ideeen/{idea_id}/verberg",
        f"/admin/ideeen/{idea_id}/status",
        f"/admin/ideeen/{idea_id}/promoot",
    ):
        resp = client.post(path, headers={"X-CSRF-Token": token}, data={"status": "gepland"})
        assert resp.status_code == 403, path


def test_admin_hide_removes_from_member_list(make_client, seed, SessionTest):
    from app.models import Idea

    idea_id = _new_idea(SessionTest, seed["member"], title="Verborgen idee")

    admin = make_client(seed["admin"])
    admin_token = csrf_token(admin, "/ideeen")
    resp = admin.post(
        f"/admin/ideeen/{idea_id}/verberg", headers={"X-CSRF-Token": admin_token}
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        assert s.get(Idea, idea_id).hidden is True
    finally:
        s.close()

    # The member-facing list no longer shows the hidden idea.
    member = make_client(seed["member"])
    listing = member.get("/ideeen")
    assert "Verborgen idee" not in listing.text


def test_admin_set_status(make_client, seed, SessionTest):
    from app.models import Idea, IdeaStatus

    idea_id = _new_idea(SessionTest, seed["member"])
    admin = make_client(seed["admin"])
    token = csrf_token(admin, "/ideeen")
    resp = admin.post(
        f"/admin/ideeen/{idea_id}/status",
        data={"status": "gedaan"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        assert s.get(Idea, idea_id).status is IdeaStatus.gedaan
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Promotie -> RoadmapItem (kern)                                              #
# --------------------------------------------------------------------------- #
def test_admin_promote_creates_roadmap_item(make_client, seed, SessionTest):
    from app.models import AuditAction, AuditLog, Idea, IdeaStatus, RoadmapItem

    idea_id = _new_idea(SessionTest, seed["member"], title="Te promoten")

    admin = make_client(seed["admin"])
    token = csrf_token(admin, "/ideeen")
    resp = admin.post(
        f"/admin/ideeen/{idea_id}/promoot", headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        items = s.query(RoadmapItem).all()
        assert len(items) == 1
        assert items[0].linked_idea_id == idea_id
        # Promoted idea status flips to gepland.
        assert s.get(Idea, idea_id).status is IdeaStatus.gepland
        audits = (
            s.query(AuditLog)
            .filter(AuditLog.action == AuditAction.idea_promoted)
            .all()
        )
        assert len(audits) == 1
    finally:
        s.close()
