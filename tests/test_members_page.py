"""Publieke ledenpagina (L2) — alleen PUBLIEKE profielen + filter/zoek.

Twee niveaus:
- service ``list_public_profiles`` (rollback-geïsoleerde ``db``): poort +
  tag/maakt/zoekt-filters geven exact de juiste subset.
- HTTP ``GET /leden`` (wegwerp-engine): besloten/geschorst lekt nooit in de
  constellatie; htmx-fragment vs. volledige pagina.
"""

from __future__ import annotations

import pytest
from app.models import (
    Base,
    Member,
    MemberStatus,
    Profile,
    Tag,
    Visibility,
)
from app.services import members_service
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Service-laag — poort + filters                                              #
# --------------------------------------------------------------------------- #
def test_only_public_approved_profiles_listed(db, make_member, make_profile):
    pub = make_member(email="pub@example.com", name="Publiek Lid")
    make_profile(pub, visibility=Visibility.public)

    members_only_owner = make_member(email="closed@example.com", name="Besloten")
    make_profile(members_only_owner, visibility=Visibility.members)

    suspended = make_member(
        email="susp@example.com", name="Geschorst", status=MemberStatus.suspended
    )
    make_profile(suspended, visibility=Visibility.public)  # public maar geschorst

    rows = members_service.list_public_profiles(db)
    names = {p.display_name for p in rows}
    assert "Publiek Lid" in names
    assert "Besloten" not in names  # members-only → niet in constellatie
    assert "Geschorst" not in names  # public maar owner geschorst → offline


def test_filter_by_tag(db, make_member, make_profile):
    a = make_member(email="a@example.com", name="Alfa")
    pa = make_profile(a, visibility=Visibility.public)
    b = make_member(email="b@example.com", name="Beta")
    pb = make_profile(b, visibility=Visibility.public)

    zorg = Tag(name="Zorg", slug="zorg")
    tech = Tag(name="Tech", slug="tech")
    db.add_all([zorg, tech])
    db.flush()
    pa.tags = [zorg]
    pb.tags = [tech]
    db.flush()

    rows = members_service.list_public_profiles(db, tag="zorg")
    assert {p.display_name for p in rows} == {"Alfa"}


def test_filter_by_maakt_matches_offering_or_summary(
    db, make_member, make_profile, make_offering
):
    a = make_member(email="m1@example.com", name="Maker A")
    pa = make_profile(a, visibility=Visibility.public)
    make_offering(pa, title="Zorgrobot voor ouderen")

    b = make_member(email="m2@example.com", name="Maker B")
    make_profile(
        b, visibility=Visibility.public, makes_summary="Ik maak waterzuivering"
    )

    c = make_member(email="m3@example.com", name="Maker C")
    make_profile(c, visibility=Visibility.public)

    rows_robot = members_service.list_public_profiles(db, maakt="Zorgrobot")
    assert {p.display_name for p in rows_robot} == {"Maker A"}

    rows_water = members_service.list_public_profiles(db, maakt="waterzuivering")
    assert {p.display_name for p in rows_water} == {"Maker B"}


def test_filter_by_zoekt_matches_need(db, make_member, make_profile):
    from app.models import Need

    a = make_member(email="z1@example.com", name="Zoeker A")
    pa = make_profile(a, visibility=Visibility.public)
    db.add(Need(profile_id=pa.id, title="Zoek een frontend-bouwer", position=0))
    db.flush()

    b = make_member(email="z2@example.com", name="Zoeker B")
    make_profile(b, visibility=Visibility.public)

    rows = members_service.list_public_profiles(db, zoekt="frontend")
    assert {p.display_name for p in rows} == {"Zoeker A"}


def test_blank_filters_are_ignored(db, make_member, make_profile):
    a = make_member(email="blank@example.com", name="Iedereen")
    make_profile(a, visibility=Visibility.public)
    rows = members_service.list_public_profiles(db, tag="  ", maakt="", zoekt=None)
    assert len(rows) == 1


# --------------------------------------------------------------------------- #
# HTTP-laag — /leden lekt geen besloten/geschorst                            #
# --------------------------------------------------------------------------- #
@pytest.fixture
def page_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

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
def client(page_engine):
    from app.db import get_db
    from app.main import app
    from sqlalchemy.orm import sessionmaker

    SessionTest = sessionmaker(bind=page_engine, autoflush=False, future=True)

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


def _seed(page_engine):
    from sqlalchemy.orm import Session

    with Session(page_engine) as s:
        pub = Member(
            email="pub@example.com", name="Zichtbaar Lid", status=MemberStatus.approved
        )
        closed = Member(
            email="closed@example.com",
            name="Verborgen Lid",
            status=MemberStatus.approved,
        )
        s.add_all([pub, closed])
        s.flush()
        s.add_all(
            [
                Profile(
                    member_id=pub.id,
                    slug="zichtbaar-lid",
                    display_name="Zichtbaar Lid",
                    visibility=Visibility.public,
                ),
                Profile(
                    member_id=closed.id,
                    slug="verborgen-lid",
                    display_name="Verborgen Lid",
                    visibility=Visibility.members,
                ),
            ]
        )
        s.commit()


def test_leden_page_lists_public_hides_closed(client, page_engine):
    _seed(page_engine)
    resp = client.get("/leden")
    assert resp.status_code == 200
    assert "Zichtbaar Lid" in resp.text
    assert "Verborgen Lid" not in resp.text


def test_leden_htmx_returns_grid_fragment(client, page_engine):
    _seed(page_engine)
    resp = client.get("/leden", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    # Het fragment is geen volledige HTML-document (geen <html>/<head>).
    assert "<html" not in resp.text.lower()


def test_leden_empty_state_renders(client, page_engine):
    # Geen profielen geseed → lege constellatie rendert zonder fout.
    resp = client.get("/leden")
    assert resp.status_code == 200
