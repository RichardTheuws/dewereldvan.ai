"""Tests voor "Dichtbij" — grof + opt-in locatie (PRD-samenkomen, fase 2).

Kernen die we bewaken:
- geo_service reduceert vrije postcode-invoer tot een 2-cijferig gebied + middelpunt
  (nooit een exact adres), haversine + banden kloppen;
- location_service zet/wist alleen de grove velden, garbage raakt niets aan;
- de auto-selectie krijgt een grove afstandsband bovenop de interesse-graaf en zet
  nabije makers vooraan — degradeert netjes als er geen locatie is;
- de opt-in-routes zijn login-gated en de htmx-swap werkt.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import GatheringVoteChoice
from app.services import gathering_service, geo_service, location_service
from tests._route_helpers import csrf_token, make_route_engine


def _future(days: int) -> datetime:
    return (datetime.now() + timedelta(days=days)).replace(
        hour=19, minute=0, second=0, microsecond=0
    )


# --------------------------------------------------------------------------- #
# geo_service                                                                  #
# --------------------------------------------------------------------------- #


def test_resolve_reduces_postcode_to_area():
    for raw in ("3511 AB", "3511", "35", " 35 "):
        area = geo_service.resolve(raw)
        assert area is not None
        assert area.code == "35"
        assert "Utrecht" in area.label


def test_resolve_rejects_unknown_or_short():
    assert geo_service.resolve("") is None
    assert geo_service.resolve("3") is None  # < 2 cijfers
    assert geo_service.resolve("ABCD") is None
    assert geo_service.resolve("09xx") is None  # bestaat niet in NL (10-99)


def test_haversine_amsterdam_rotterdam():
    # Amsterdam (~52.37, 4.90) ↔ Rotterdam (~51.92, 4.48): ~57 km hemelsbreed.
    d = geo_service.haversine_km(52.37, 4.90, 51.92, 4.48)
    assert 50 < d < 70


def test_band_thresholds():
    assert geo_service.band(10) == "<25 km"
    assert geo_service.band(40) == "~25–50 km"
    assert geo_service.band(80) is None  # te ver = geen 'dichtbij'-label
    assert geo_service.band(None) is None


# --------------------------------------------------------------------------- #
# location_service                                                             #
# --------------------------------------------------------------------------- #


def test_set_area_stores_only_coarse(db, make_member, make_profile):
    m = make_member()
    p = make_profile(m)
    area = location_service.set_area(db, p, "3511 AB")
    assert area is not None
    assert p.area_code == "35"
    assert p.area_lat is not None and p.area_lng is not None
    assert location_service.has_area(p)


def test_set_area_rejects_garbage_untouched(db, make_member, make_profile):
    m = make_member()
    p = make_profile(m)
    assert location_service.set_area(db, p, "geen postcode") is None
    assert p.area_code is None
    assert not location_service.has_area(p)


def test_clear_area(db, make_member, make_profile):
    m = make_member()
    p = make_profile(m)
    location_service.set_area(db, p, "3511")
    location_service.clear_area(db, p)
    assert p.area_code is None and p.area_lat is None
    assert not location_service.has_area(p)


# --------------------------------------------------------------------------- #
# Auto-selectie mét afstandsband (Dichtbij bovenop de interesse-graaf)         #
# --------------------------------------------------------------------------- #


def test_suggest_annotates_distance_and_sorts_near_first(db, make_member, make_profile):
    from app.models import Tag

    creator = make_member(email="c@example.com")
    cp = make_profile(creator)
    location_service.set_area(db, cp, "3511")  # Utrecht (35)

    near = make_member(email="near@example.com")
    npf = make_profile(near, display_name="Nabij Maker")
    location_service.set_area(db, npf, "3811")  # Amersfoort (38) ~20 km

    far = make_member(email="far@example.com")
    fpf = make_profile(far, display_name="Ver Maker")
    location_service.set_area(db, fpf, "9401")  # Groningen (94) ~150 km

    tag = Tag(name="voice-agents", slug="voice-agents")
    db.add(tag)
    db.flush()
    for pf in (npf, fpf):
        pf.tags.append(tag)
    db.flush()

    g = gathering_service.create(
        db, creator=creator, title="Borrel", interest="voice-agents",
        date_options=[_future(3)],
    )
    suggested = gathering_service.suggest_interested(db, g)
    by_slug = {s.profile.slug: s for s in suggested}
    assert by_slug[npf.slug].distance_band is not None  # nabij → band
    assert by_slug[fpf.slug].distance_band is None  # te ver → geen band
    # Nabije maker staat vooraan.
    assert suggested[0].profile.slug == npf.slug


def test_suggest_without_creator_area_has_no_bands(db, make_member, make_profile):
    from app.models import Tag

    creator = make_member(email="c@example.com")
    make_profile(creator)  # geen locatie
    other = make_member(email="o@example.com")
    op = make_profile(other, display_name="Maker")
    location_service.set_area(db, op, "3811")
    tag = Tag(name="voice-agents", slug="voice-agents")
    db.add(tag)
    db.flush()
    op.tags.append(tag)
    db.flush()

    g = gathering_service.create(
        db, creator=creator, title="X", interest="voice-agents", date_options=[_future(3)]
    )
    suggested = gathering_service.suggest_interested(db, g)
    assert all(s.distance_band is None for s in suggested)  # geen maker-locatie → geen banden


# --------------------------------------------------------------------------- #
# Routes                                                                       #
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
    from app.models import Member, MemberStatus, Profile, Visibility

    s = SessionTest()
    m = Member(email="lid@example.com", name="Lid", status=MemberStatus.approved)
    s.add(m)
    s.flush()
    s.add(Profile(member_id=m.id, slug="lid", display_name="Lid", visibility=Visibility.public))
    s.commit()
    mid = m.id
    s.close()
    return {"member": mid}


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
            return db.get(Member, member_id) if member_id is not None else None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def test_page_requires_login(make_client):
    resp = make_client(None).get("/profiel/dichtbij", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/login")


def test_set_and_clear_area_flow(make_client, SessionTest, seed):
    client = make_client(seed["member"])
    token = csrf_token(client, "/profiel/dichtbij")

    ok = client.post("/profiel/dichtbij", data={"postcode": "3511 AB"},
                     headers={"X-CSRF-Token": token})
    assert ok.status_code == 200
    assert "Utrecht" in ok.text and "Wis mijn gebied" in ok.text

    # Onherkenbaar → nette hint, niets opgeslagen.
    bad = client.post("/profiel/dichtbij", data={"postcode": "xyz"},
                      headers={"X-CSRF-Token": token})
    # (gebied stond al gezet; de fout-render toont de foutmelding)
    assert bad.status_code == 400

    cleared = client.post("/profiel/dichtbij/wis", data={},
                          headers={"X-CSRF-Token": token})
    assert cleared.status_code == 200
    assert "Je postcode" in cleared.text  # terug naar het invoer-formulier
