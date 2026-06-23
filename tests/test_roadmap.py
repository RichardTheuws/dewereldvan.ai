"""Tests for the roadmap (E3): zichtbaarheid, admin-CRUD, en promote->SET NULL.

The headline guarantees:
- ``/roadmap`` is **publiek** (anon -> 200, indexeerbaar), items als een echt
  kanban gegroepeerd per **status** (overwegen → gepland → bezig → gedaan) en
  binnen een kolom op positie geordend.
- Admin CRUD mutates the DB; non-admins get 403.
- After promoting an idea to a roadmap item, deleting that idea NULLs the item's
  ``linked_idea_id`` (FK ondelete=SET NULL) — the item survives.

No network. Throwaway engine per test.
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
    return sessionmaker(bind=route_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def seed(SessionTest):
    from app.models import Member, MemberRole, MemberStatus

    s = SessionTest()
    member = Member(email="lid@example.com", name="Lid", status=MemberStatus.approved)
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


# --------------------------------------------------------------------------- #
# Zichtbaarheid                                                                #
# --------------------------------------------------------------------------- #
def test_roadmap_public_for_anon(make_client):
    """De roadmap is publiek + indexeerbaar (geen login-redirect, geen noindex)."""
    client = make_client(None)
    resp = client.get("/roadmap", follow_redirects=False)
    assert resp.status_code == 200
    assert 'name="robots" content="noindex' not in resp.text
    # De vier vaste kanban-kolommen staan er altijd (ook leeg).
    for label in ("Overwegen", "Gepland", "In aanbouw", "Gelanceerd"):
        assert label in resp.text


def test_roadmap_member_ok(make_client, seed):
    client = make_client(seed["member"])
    assert client.get("/roadmap").status_code == 200


def test_roadmap_item_shows_grounded_idea_origin(make_client, seed, SessionTest):
    """Een gepromoot item toont de gegronde herkomst: welk lid-idee het voedt +
    het aantal stemmen, klikbaar naar het idee (levend/transparant, geen migratie)."""
    from app.models import Idea, IdeaVote, RoadmapItem, RoadmapStatus

    with SessionTest() as s:
        idea = Idea(member_id=seed["member"], title="Een goed idee", body="Doe X.")
        s.add(idea)
        s.flush()
        iid = idea.id
        s.add(IdeaVote(idea_id=iid, member_id=seed["admin"]))
        s.add(
            RoadmapItem(
                title="Gepromoot item", phase="Nu", position=0,
                status=RoadmapStatus.overwegen, linked_idea_id=iid,
            )
        )
        s.commit()

    resp = make_client(seed["member"]).get("/roadmap")
    assert resp.status_code == 200
    body = resp.text
    assert "uit een idee van Lid" in body
    assert "1 stem" in body
    assert f"/ideeen#idea-{iid}" in body


def test_roadmap_groups_by_status_in_position_order(make_client, seed, SessionTest):
    from app.models import RoadmapItem, RoadmapStatus

    s = SessionTest()
    s.add_all(
        [
            RoadmapItem(title="Bezig-eerst", status=RoadmapStatus.bezig, phase="Nu", position=0),
            RoadmapItem(title="Bezig-tweede", status=RoadmapStatus.bezig, phase="Nu", position=1),
            RoadmapItem(
                title="Overweeg-item", status=RoadmapStatus.overwegen, phase="Later", position=5
            ),
        ]
    )
    s.commit()
    s.close()

    client = make_client(seed["member"])
    resp = client.get("/roadmap")
    assert resp.status_code == 200
    body = resp.text
    for title in ("Bezig-eerst", "Bezig-tweede", "Overweeg-item"):
        assert title in body
    # Binnen de "bezig"-kolom rendert positie 0 vóór positie 1.
    assert body.index("Bezig-eerst") < body.index("Bezig-tweede")
    # Kolom-leesvolgorde: overwegen-kolom staat vóór de bezig-kolom.
    assert body.index("Overweeg-item") < body.index("Bezig-eerst")


def test_list_by_status_always_four_columns(SessionTest):
    """Een echt kanban: alle vier de status-kolommen komen terug, óók de lege,
    in vaste leesvolgorde."""
    from app.models import RoadmapItem, RoadmapStatus
    from app.services import roadmap_service

    s = SessionTest()
    s.add(RoadmapItem(title="Eén ding", status=RoadmapStatus.gedaan, phase="X", position=0))
    s.commit()
    cols = roadmap_service.list_by_status(s)
    assert [status.value for status, _label, _items in cols] == [
        "overwegen", "gepland", "bezig", "gedaan",
    ]
    # gedaan-kolom heeft het item; de rest is leeg (maar wel aanwezig).
    by_status = {status.value: items for status, _label, items in cols}
    assert [i.title for i in by_status["gedaan"]] == ["Eén ding"]
    assert by_status["overwegen"] == [] and by_status["gepland"] == []
    s.close()


# --------------------------------------------------------------------------- #
# Admin CRUD + poort                                                           #
# --------------------------------------------------------------------------- #
def test_admin_board_requires_admin(make_client, seed):
    member_client = make_client(seed["member"])
    assert member_client.get("/admin/roadmap").status_code == 403

    admin_client = make_client(seed["admin"])
    assert admin_client.get("/admin/roadmap").status_code == 200


def test_admin_create_item(make_client, seed, SessionTest):
    from app.models import RoadmapItem

    admin = make_client(seed["admin"])
    token = csrf_token(admin, "/admin/roadmap")
    resp = admin.post(
        "/admin/roadmap",
        data={
            "title": "Nieuwe mijlpaal",
            "description": "iets moois",
            "status": "gepland",
            "phase": "Volgende",
            "position": 0,
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        items = s.query(RoadmapItem).all()
        assert len(items) == 1
        assert items[0].title == "Nieuwe mijlpaal"
        assert items[0].phase == "Volgende"
    finally:
        s.close()


def test_admin_update_item(make_client, seed, SessionTest):
    from app.models import RoadmapItem, RoadmapStatus

    s = SessionTest()
    item = RoadmapItem(title="Oud", status=RoadmapStatus.overwegen, phase="Later", position=0)
    s.add(item)
    s.commit()
    item_id = item.id
    s.close()

    admin = make_client(seed["admin"])
    token = csrf_token(admin, "/admin/roadmap")
    resp = admin.post(
        f"/admin/roadmap/{item_id}/bewerken",
        data={"title": "Nieuw", "status": "bezig", "phase": "Nu", "position": 2},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200

    s = SessionTest()
    try:
        item = s.get(RoadmapItem, item_id)
        assert item.title == "Nieuw"
        assert item.status is RoadmapStatus.bezig
        assert item.phase == "Nu"
    finally:
        s.close()


def test_admin_delete_item(make_client, seed, SessionTest):
    from app.models import RoadmapItem, RoadmapStatus

    s = SessionTest()
    item = RoadmapItem(title="Weg", status=RoadmapStatus.overwegen, phase="Later", position=0)
    s.add(item)
    s.commit()
    item_id = item.id
    s.close()

    admin = make_client(seed["admin"])
    token = csrf_token(admin, "/admin/roadmap")
    resp = admin.post(f"/admin/roadmap/{item_id}/verwijderen", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200

    s = SessionTest()
    try:
        assert s.get(RoadmapItem, item_id) is None
    finally:
        s.close()


def test_admin_create_blank_title_rejected(make_client, seed, SessionTest):
    from app.models import RoadmapItem

    admin = make_client(seed["admin"])
    token = csrf_token(admin, "/admin/roadmap")
    resp = admin.post(
        "/admin/roadmap",
        data={"title": "   ", "phase": "Later"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400
    s = SessionTest()
    try:
        assert s.query(RoadmapItem).count() == 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Promote -> SET NULL on idea delete (kern)                                   #
# --------------------------------------------------------------------------- #
def test_promote_then_delete_idea_nulls_link_keeps_item(db, make_member, make_idea):
    """Deleting a promoted idea NULLs linked_idea_id; the roadmap item survives.

    Uses SQLite with PRAGMA foreign_keys=ON so the ondelete=SET NULL FK actually
    fires (SQLite ignores FK actions unless the pragma is enabled).
    """
    from app.models import RoadmapItem
    from app.services import idea_service
    from sqlalchemy import text

    db.execute(text("PRAGMA foreign_keys=ON"))

    admin = make_member(email="admin@example.com")
    author = make_member(email="author@example.com")
    idea = make_idea(author, title="Promoot-en-verwijder")

    item = idea_service.promote(db, idea, actor=admin)
    db.flush()
    item_id = item.id
    assert item.linked_idea_id == idea.id

    # Delete the idea; its votes cascade, the roadmap link goes NULL.
    db.delete(idea)
    db.flush()

    db.expire_all()
    surviving = db.get(RoadmapItem, item_id)
    assert surviving is not None
    assert surviving.linked_idea_id is None
