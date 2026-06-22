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
# Discipline-filter (Fase D) — mapt op de kind van de werk-items              #
# --------------------------------------------------------------------------- #
def test_discipline_filter_matches_offering_kind(db, make_member, make_profile, make_offering):
    from app.models import OfferingKind

    vid_m = make_member(email="vid@example.com", name="Video Maker")
    vid_p = make_profile(vid_m, visibility=Visibility.public)
    vo = make_offering(vid_p, title="Mijn showreel")
    vo.kind = OfferingKind.video

    bld_m = make_member(email="bld@example.com", name="Bouwer")
    bld_p = make_profile(bld_m, visibility=Visibility.public)
    make_offering(bld_p, title="Mijn SaaS")  # default kind=project
    db.flush()

    vids = members_service.list_public_profiles(db, discipline="video")
    assert [p.id for p in vids] == [vid_p.id]

    bouwers = members_service.list_public_profiles(db, discipline="bouwer")
    assert [p.id for p in bouwers] == [bld_p.id]

    # Onbekende/lege discipline → genegeerd (beide profielen).
    assert len(members_service.list_public_profiles(db, discipline="zzz")) == 2
    assert len(members_service.list_public_profiles(db, discipline="")) == 2


def test_derive_disciplines_from_offering_kinds(db, make_member, make_profile, make_offering):
    from app.models import OfferingKind

    m = make_member(email="multi@example.com", name="Multi")
    p = make_profile(m, visibility=Visibility.public)
    o1 = make_offering(p, title="Workshop")
    o1.kind = OfferingKind.workshop
    o2 = make_offering(p, title="Showreel")
    o2.kind = OfferingKind.video
    db.flush()

    labels = members_service.derive_disciplines(p)
    # Vaste volgorde (DISCIPLINES); kaart-labels zijn enkelvoud (Video-AI vóór Trainer).
    assert labels == ["Video-AI", "Trainer"]


def test_discipline_options_shape():
    opts = members_service.discipline_options()
    slugs = [s for s, _l in opts]
    assert "video" in slugs and "trainer" in slugs and "publicaties" in slugs
    assert all(isinstance(label, str) for _s, label in opts)


# --------------------------------------------------------------------------- #
# select_living_stars — tijd-bewuste constellatie (slice 2)                   #
# --------------------------------------------------------------------------- #
def test_select_living_stars_new_first_with_ids_and_count(db, make_member, make_profile):
    """Pas-verschenen makers schuiven naar voren + worden als 'nieuw' gemarkeerd."""
    from datetime import timedelta

    from app.security import naive_utc, utcnow

    now = utcnow()
    old_m = make_member(email="oud@example.com", name="Oud")
    old_m.created_at = naive_utc(now) - timedelta(days=30)
    new_m = make_member(email="nieuw@example.com", name="Nieuw")
    new_m.created_at = naive_utc(now) - timedelta(days=2)
    db.flush()
    old_p = make_profile(old_m, display_name="Oud")
    new_p = make_profile(new_m, display_name="Nieuw")

    stars, new_ids, count = members_service.select_living_stars(
        [old_p, new_p], now=now
    )
    assert stars[0].id == new_p.id            # nieuw eerst (zichtbaar in de slice)
    assert new_ids == {new_p.id}              # alleen de nieuwe gloeit
    assert count == 1                         # totaal-telling voor de kop


def test_select_living_stars_count_includes_makers_beyond_slice(
    db, make_member, make_profile
):
    """new_count telt ALLE nieuwe makers, ook buiten de zichtbare ``limit``."""
    from datetime import timedelta

    from app.security import naive_utc, utcnow

    now = utcnow()
    profiles = []
    for i in range(5):
        m = make_member(email=f"m{i}@example.com", name=f"Maker {i}")
        m.created_at = naive_utc(now) - timedelta(days=1)
        db.flush()
        profiles.append(make_profile(m, display_name=f"Maker {i}"))

    stars, new_ids, count = members_service.select_living_stars(
        profiles, now=now, limit=2
    )
    assert len(stars) == 2          # slice gerespecteerd
    assert len(new_ids) == 2        # alleen de zichtbare nieuwe gloeien
    assert count == 5               # maar de kop weet: 5 nieuw


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


def _seed_connected(page_engine):
    """Twee publieke makers die één tag + één tool delen (graaf-buren)."""
    from app.models import Tool
    from sqlalchemy.orm import Session

    with Session(page_engine) as s:
        tag = Tag(name="Agents", slug="agents")
        tool = Tool(name="Cursor", slug="cursor")
        s.add_all([tag, tool])
        s.flush()
        for nm, slug in (("Een Maker", "een-maker"), ("Twee Maker", "twee-maker")):
            m = Member(email=f"{slug}@x.nl", name=nm, status=MemberStatus.approved)
            s.add(m)
            s.flush()
            p = Profile(
                member_id=m.id, slug=slug, display_name=nm,
                visibility=Visibility.public,
            )
            p.tags.append(tag)
            p.tools.append(tool)
            s.add(p)
        s.commit()


def test_tool_filter_empty_shows_filtered_message_not_no_members(client, page_engine):
    """Bug-fix: een tool-only filter zonder resultaat toont 'Niets gevonden'
    (gefilterd-leeg), niet 'Nog geen profielen' (helemaal-leeg)."""
    _seed(page_engine)  # publieke profielen bestaan, maar zonder tools
    resp = client.get("/leden?tool=onbestaand")
    assert resp.status_code == 200
    assert "Niets gevonden" in resp.text
    assert "Nog geen profielen" not in resp.text


def test_leden_shows_connection_signal(client, page_engine):
    """De ledengids is een verbonden graaf: een kaart toont z'n graaf-graad."""
    _seed_connected(page_engine)
    resp = client.get("/leden")
    assert resp.status_code == 200
    assert "verbonden met 1 maker" in resp.text


def test_leden_filter_autocomplete_from_vocabulary(client, page_engine):
    """Slimme filter: datalists met de echte tag/tool-vocabulaire op de volle pagina."""
    _seed_connected(page_engine)
    resp = client.get("/leden")
    assert 'list="vocab-tags"' in resp.text
    assert 'list="vocab-tools"' in resp.text
    assert "Agents" in resp.text
    assert "Cursor" in resp.text
