"""De voordeur toont de community, niet de beheerder (v0.120.2).

- Uitgelichte makers: de beheerder staat er niet tussen en de keuze roteert per dag.
- Nieuws op de voordeur is algemeen nieuws; artikelen óver een lid horen op het profiel.
- Wist een lid zichzelf, dan gaat nieuws over dat lid mee (geen wees-items die als
  redactie-nieuws publiek worden).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from app.models import (
    Member,
    MemberRole,
    MemberStatus,
    NewsRole,
    Post,
    PostKind,
    Profile,
    Visibility,
)
from app.services import directory_service
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tests._route_helpers import make_route_engine


# --------------------------------------------------------------------------- #
# Uitgelichte makers                                                          #
# --------------------------------------------------------------------------- #
def _fake(pid: int, *, admin: bool = False, photo: bool = True):
    role = MemberRole.admin if admin else MemberRole.member
    return SimpleNamespace(
        id=pid,
        photo_url="/u/x.jpg" if photo else None,
        completeness=100,
        display_name=f"Maker {pid}",
        member=SimpleNamespace(role=role),
    )


@pytest.fixture
def with_work(monkeypatch):
    monkeypatch.setattr(directory_service, "_disciplines", lambda p: ["Developer"])


def test_featured_never_includes_admin(with_work):
    profiles = [_fake(1, admin=True)] + [_fake(i) for i in range(2, 7)]
    day = date(2026, 11, 4)
    for offset in range(60):
        picked = directory_service.featured_makers(profiles, today=day + timedelta(offset))
        assert 1 not in [p.id for p in picked]
        assert len(picked) == 4


def test_featured_rotates_and_everyone_gets_a_turn(with_work):
    profiles = [_fake(i) for i in range(1, 9)]
    day = date(2026, 11, 4)
    seen: set[int] = set()
    selections = set()
    for offset in range(30):
        picked = directory_service.featured_makers(profiles, today=day + timedelta(offset))
        seen.update(p.id for p in picked)
        selections.add(tuple(sorted(p.id for p in picked)))
    assert seen == set(range(1, 9))
    assert len(selections) > 1


def test_featured_stable_within_a_day_and_photo_first(with_work):
    profiles = [_fake(i, photo=False) for i in range(1, 5)] + [_fake(i) for i in range(5, 9)]
    day = date(2026, 11, 4)
    a = directory_service.featured_makers(profiles, today=day)
    b = directory_service.featured_makers(list(reversed(profiles)), today=day)
    assert [p.id for p in a] == [p.id for p in b]
    assert all(p.photo_url for p in a)


# --------------------------------------------------------------------------- #
# Wissen: nieuws over het lid gaat mee                                         #
# --------------------------------------------------------------------------- #
def test_delete_removes_news_about_member_keeps_shared(db, make_member):
    from app.services.account_deletion import delete_member_completely

    m = make_member(email="weg@example.com")
    for title, role in [
        ("Over mij", NewsRole.vermeld),
        ("Mijn blog", NewsRole.geschreven),
        ("Interview", NewsRole.geinterviewd),
        ("Leuk artikel", NewsRole.gedeeld),
    ]:
        db.add(Post(added_by_id=m.id, kind=PostKind.nieuws, title=title, role=role))
    db.flush()

    delete_member_completely(db, m)
    db.flush()

    left = db.scalars(select(Post)).all()
    assert [p.title for p in left] == ["Leuk artikel"]
    assert left[0].added_by_id is None


# --------------------------------------------------------------------------- #
# Voordeur-route                                                               #
# --------------------------------------------------------------------------- #
@pytest.fixture
def SessionTest():
    eng = make_route_engine()
    yield sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    eng.dispose()


@pytest.fixture
def client(SessionTest):
    from app.db import get_db
    from app.main import app

    def _override_get_db():
        s = SessionTest()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.clear()


def test_home_news_skips_articles_about_members(client, SessionTest):
    with SessionTest() as s:
        m = Member(email="lid@example.com", name="Lid", status=MemberStatus.approved)
        s.add(m)
        s.flush()
        s.add(Profile(member_id=m.id, slug="lid", display_name="Lid", visibility=Visibility.public))
        s.add_all(
            [
                Post(
                    added_by_id=m.id,
                    kind=PostKind.nieuws,
                    title="Bedrijf van Lid in de krant",
                    url="https://example.com/krant",
                    role=NewsRole.vermeld,
                ),
                Post(
                    kind=PostKind.nieuws,
                    title="Nieuw open-weight model verschenen",
                    url="https://example.com/model",
                    source_kind="ai_curated",
                ),
            ]
        )
        s.commit()

    html = client.get("/").text
    assert "Nieuw open-weight model verschenen" in html
    assert "Bedrijf van Lid in de krant" not in html
