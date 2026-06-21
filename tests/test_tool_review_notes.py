"""Tests voor het mens-naast-AI-correctiepad (doc 03 §4.3, Fase C).

Twee lagen, gespiegeld van test_feedback/test_news_briefing:
- **Service** op de rollback-geïsoleerde ``db``-fixture: add_note verschijnt in
  list_notes, rate-limit grijpt na N, body-cap, hide_note (hidden=True, weg uit
  list_notes, AuditLog), en — de kern — een note overschrijft ``tool.tool_review``
  NOOIT (apart model, apart getoond).
- **Route** op een wegwerp-engine (commits lekken niet): een anonieme bezoeker kan
  GEEN note posten (require_member → redirect), een lid wél, admin verbergt, en
  ``herzie`` is admin-only (gewoon lid → 403).
"""

from __future__ import annotations

import pytest
from app.models import (
    AuditAction,
    AuditLog,
    MemberRole,
    MemberStatus,
    Tool,
    ToolReviewNote,
)
from app.services import tool_review_note_service
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests._route_helpers import csrf_token, make_route_engine


_GOOD_REVIEW = {
    "one_liner": "Een agent-framework.",
    "good_for": ["RAG"],
    "for_whom": "Solo-builders.",
    "strengths": ["community"],
    "limitations": ["abstractie verbergt detail"],
    "pricing_model": "gratis tier",
    "nlbe_relevance": None,
    "confidence": "high",
}


def _make_tool(db, *, name="Acme", url="https://acme.example", review=None) -> Tool:
    tool = Tool(name=name, slug=name.lower(), url=url)
    if review is not None:
        tool.tool_review = review
        tool.tool_review_status = "ok"
    db.add(tool)
    db.flush()
    return tool


# --------------------------------------------------------------------------- #
# Service: een lid voegt een note toe -> verschijnt in list_notes              #
# --------------------------------------------------------------------------- #
def test_add_note_appears_in_list(db, make_member):
    member = make_member()
    tool = _make_tool(db)
    note = tool_review_note_service.add_note(
        db, tool=tool, member=member, field="limitations", body="Klopt niet meer."
    )
    assert note.id is not None
    notes = tool_review_note_service.list_notes(db, tool)
    assert len(notes) == 1
    assert notes[0].body == "Klopt niet meer."
    assert notes[0].field == "limitations"
    assert notes[0].member_id == member.id


# --------------------------------------------------------------------------- #
# KERN: een note overschrijft de AI-review NOOIT (apart model, apart getoond)  #
# --------------------------------------------------------------------------- #
def test_note_does_not_overwrite_ai_review(db, make_member):
    member = make_member()
    tool = _make_tool(db, review=dict(_GOOD_REVIEW))
    tool_review_note_service.add_note(
        db, tool=tool, member=member, field="limitations",
        body="Mijn correctie op de AI.",
    )
    db.flush()
    # De AI-review is ONGEWIJZIGD — de note is een aparte rij.
    assert tool.tool_review == _GOOD_REVIEW
    assert tool.tool_review_status == "ok"
    # En de note leeft in een eigen tabel.
    rows = db.scalars(
        select(ToolReviewNote).where(ToolReviewNote.tool_id == tool.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].body == "Mijn correctie op de AI."


# --------------------------------------------------------------------------- #
# Empty field -> None (algemeen); body-cap                                     #
# --------------------------------------------------------------------------- #
def test_empty_field_is_general_and_body_capped(db, make_member):
    member = make_member()
    tool = _make_tool(db)
    note = tool_review_note_service.add_note(
        db, tool=tool, member=member, field="   ", body="x" * 9000
    )
    assert note.field is None  # leeg veld = algemene aanvulling
    from app.config import settings

    assert len(note.body) == settings.max_feedback_body_chars


# --------------------------------------------------------------------------- #
# Rate-limit grijpt na N                                                        #
# --------------------------------------------------------------------------- #
def test_rate_limit_after_n(db, make_member, monkeypatch):
    monkeypatch.setattr(
        tool_review_note_service.settings, "rate_limit_tool_note_per_hour", 3
    )
    member = make_member()
    tool = _make_tool(db)
    for _ in range(3):
        tool_review_note_service.check_tool_note_rate_limit(db, member)
        tool_review_note_service.add_note(
            db, tool=tool, member=member, field=None, body="aanvulling"
        )
        db.flush()
    with pytest.raises(tool_review_note_service.ToolNoteRateLimited):
        tool_review_note_service.check_tool_note_rate_limit(db, member)


# --------------------------------------------------------------------------- #
# Admin verbergt -> hidden=True, weg uit list_notes, AuditLog                   #
# --------------------------------------------------------------------------- #
def test_hide_note_removes_and_audits(db, make_member):
    member = make_member()
    admin = make_member(email="admin@x.example", role=MemberRole.admin)
    tool = _make_tool(db)
    note = tool_review_note_service.add_note(
        db, tool=tool, member=member, field=None, body="te verbergen"
    )
    db.flush()
    assert len(tool_review_note_service.list_notes(db, tool)) == 1

    tool_review_note_service.hide_note(db, note, actor=admin)
    db.flush()
    assert note.hidden is True
    assert tool_review_note_service.list_notes(db, tool) == []  # weg uit zichtbaar
    log = db.scalar(
        select(AuditLog).where(AuditLog.action == AuditAction.tool_note_hidden)
    )
    assert log is not None and log.actor_member_id == admin.id


# --------------------------------------------------------------------------- #
# Route-laag (wegwerp-engine, commits lekken niet)                             #
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
    tool = Tool(name="Acme", slug="acme", url="https://acme.example",
                tool_review=dict(_GOOD_REVIEW), tool_review_status="ok")
    s.add_all([admin, member, tool])
    s.commit()
    ids = {"admin": admin.id, "member": member.id, "tool": tool.id}
    s.close()
    return ids


def test_anonymous_cannot_post_note(make_client, seed):
    """Een uitgelogde bezoeker kan GEEN aanvulling posten (require_member)."""
    anon = make_client(None)
    token = csrf_token(anon, "/login")
    resp = anon.post(
        f"/tools/{seed['tool']}/correctie",
        data={"body": "stiekem", "field": ""},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    # require_member -> 303 redirect naar /login (geen note opgeslagen).
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_member_posts_note_via_htmx(make_client, seed, SessionTest):
    member_client = make_client(seed["member"])
    token = csrf_token(member_client, "/login")
    resp = member_client.post(
        f"/tools/{seed['tool']}/correctie",
        data={"body": "Mijn aanvulling.", "field": "limitations"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "Mijn aanvulling." in resp.text
    assert "Aangevuld door Lid" in resp.text

    # Server-side: de note bestaat en de AI-review is ONGEWIJZIGD.
    s = SessionTest()
    tool = s.get(Tool, seed["tool"])
    assert tool.tool_review == _GOOD_REVIEW  # nooit overschreven
    notes = tool_review_note_service.list_notes(s, tool)
    assert len(notes) == 1 and notes[0].body == "Mijn aanvulling."
    s.close()


def test_empty_body_is_inline_error(make_client, seed):
    member_client = make_client(seed["member"])
    token = csrf_token(member_client, "/login")
    resp = member_client.post(
        f"/tools/{seed['tool']}/correctie",
        data={"body": "   ", "field": ""},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400
    assert "Schrijf eerst" in resp.text


def test_admin_hides_note_via_htmx(make_client, seed, SessionTest):
    # Eerst een note aanmaken (door het lid).
    s = SessionTest()
    from app.models import Member

    member = s.get(Member, seed["member"])
    tool = s.get(Tool, seed["tool"])
    note = tool_review_note_service.add_note(
        s, tool=tool, member=member, field=None, body="weg ermee"
    )
    s.commit()
    note_id = note.id
    s.close()

    admin_client = make_client(seed["admin"])
    token = csrf_token(admin_client, "/login")
    resp = admin_client.post(
        f"/admin/tool-notes/{note_id}/verberg",
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "weg ermee" not in resp.text  # verborgen, niet meer in de lijst

    s2 = SessionTest()
    refreshed = s2.get(ToolReviewNote, note_id)
    assert refreshed.hidden is True
    s2.close()


def test_member_cannot_hide_note(make_client, seed, SessionTest):
    s = SessionTest()
    from app.models import Member

    member = s.get(Member, seed["member"])
    tool = s.get(Tool, seed["tool"])
    note = tool_review_note_service.add_note(
        s, tool=tool, member=member, field=None, body="probeer te verbergen"
    )
    s.commit()
    note_id = note.id
    s.close()

    member_client = make_client(seed["member"])
    token = csrf_token(member_client, "/login")
    resp = member_client.post(
        f"/admin/tool-notes/{note_id}/verberg",
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 403  # require_admin


def test_rereview_is_admin_only(make_client, seed):
    """``herzie`` ("ververs nu") is BEWUST admin-only (kostenbeheersing)."""
    member_client = make_client(seed["member"])
    token = csrf_token(member_client, "/login")
    resp = member_client.post(
        f"/tools/{seed['tool']}/herzie",
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 403  # gewoon lid geweigerd

    admin_client = make_client(seed["admin"])
    token = csrf_token(admin_client, "/login")
    resp = admin_client.post(
        f"/tools/{seed['tool']}/herzie",
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200  # admin mag
