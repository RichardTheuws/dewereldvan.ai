"""Tests voor sectie-niveau zichtbaarheid (PRD-zichtbaarheid-secties).

Kernen die we bewaken:
- de poort (`public_section_visible`): eigenaar/lid zien alles, bezoeker alleen
  publieke blokken, legacy `None` = volledig publiek (geen regressie);
- `set_public_sections`/`normalize_sections` saneren tot geldige slugs;
- ANTI-LEK: een besloten-gehouden blok lekt niet via een discovery-filter én niet
  op de detailpagina/kaart voor een bezoeker;
- leden zien elk publiek profiel altijd volledig.
"""

from __future__ import annotations

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Visibility
from app.services import members_service, visibility as vis
from tests._route_helpers import csrf_token, make_route_engine


# --------------------------------------------------------------------------- #
# Poort (service)                                                             #
# --------------------------------------------------------------------------- #


def test_normalize_sections_filters_and_orders():
    assert vis.normalize_sections(["makes", "bio", "onzin", "bio"]) == ["bio", "makes"]
    assert vis.normalize_sections([]) == []
    assert vis.normalize_sections(None) == []


def test_public_section_visible_owner_and_member_see_all(db, make_member, make_profile):
    owner = make_member(email="o@example.com")
    p = make_profile(owner, visibility=Visibility.public)
    p.public_sections = ["bio"]  # alleen bio publiek
    db.flush()
    member = make_member(email="m@example.com")
    # eigenaar + lid zien alles, ook het besloten 'needs'-blok
    assert vis.public_section_visible(p, "needs", owner) is True
    assert vis.public_section_visible(p, "needs", member) is True


def test_public_section_visible_visitor_respects_subset(db, make_member, make_profile):
    owner = make_member()
    p = make_profile(owner, visibility=Visibility.public)
    p.public_sections = ["bio"]
    db.flush()
    assert vis.public_section_visible(p, "bio", None) is True
    assert vis.public_section_visible(p, "makes", None) is False


def test_public_section_visible_legacy_none_is_full_public(db, make_member, make_profile):
    owner = make_member()
    p = make_profile(owner, visibility=Visibility.public)  # public_sections default None
    assert p.public_sections is None
    for s in vis.PUBLIC_SECTIONS:
        assert vis.public_section_visible(p, s, None) is True  # geen regressie


def test_set_public_sections_stores_normalized(db, make_member, make_profile):
    owner = make_member()
    p = make_profile(owner, visibility=Visibility.public)
    vis.set_public_sections(db, p, ["needs", "rommel", "bio"])
    assert p.public_sections == ["bio", "needs"]


# --------------------------------------------------------------------------- #
# Anti-lek in de discovery-query                                              #
# --------------------------------------------------------------------------- #


def _public_profile_with_offering(db, make_member, make_profile, make_offering, email, title):
    m = make_member(email=email)
    p = make_profile(m, display_name=email.split("@")[0], visibility=Visibility.public)
    make_offering(p, title=title)
    return p


def test_maakt_filter_hides_profile_with_private_makes(db, make_member, make_profile, make_offering):
    p = _public_profile_with_offering(db, make_member, make_profile, make_offering,
                                      "maker@example.com", "Voicebot Studio")
    p.public_sections = ["bio"]  # 'wat ik maak' besloten voor bezoekers
    db.flush()

    # Bezoeker: matcht NIET op het besloten-gehouden werk.
    visitor_hits = members_service.list_public_profiles(db, maakt="Voicebot", for_visitor=True)
    assert p.id not in {x.id for x in visitor_hits}
    # Lid: ziet alles → matcht wél.
    member_hits = members_service.list_public_profiles(db, maakt="Voicebot", for_visitor=False)
    assert p.id in {x.id for x in member_hits}


def test_maakt_filter_shows_when_makes_public(db, make_member, make_profile, make_offering):
    p = _public_profile_with_offering(db, make_member, make_profile, make_offering,
                                      "maker2@example.com", "Voicebot Studio")
    p.public_sections = ["makes"]  # publiek
    db.flush()
    hits = members_service.list_public_profiles(db, maakt="Voicebot", for_visitor=True)
    assert p.id in {x.id for x in hits}


def test_legacy_none_still_matches_for_visitor(db, make_member, make_profile, make_offering):
    p = _public_profile_with_offering(db, make_member, make_profile, make_offering,
                                      "maker3@example.com", "Voicebot Studio")
    assert p.public_sections is None  # legacy = volledig publiek
    hits = members_service.list_public_profiles(db, maakt="Voicebot", for_visitor=True)
    assert p.id in {x.id for x in hits}


# --------------------------------------------------------------------------- #
# Render (routes): bezoeker vs lid                                            #
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
    from app.models import Member, MemberStatus, Offering, OfferingKind, Profile

    s = SessionTest()
    maker = Member(email="vera@example.com", name="Vera Voice", status=MemberStatus.approved)
    watcher = Member(email="lid@example.com", name="Ander Lid", status=MemberStatus.approved)
    s.add_all([maker, watcher]); s.flush()
    p = Profile(
        member_id=maker.id, slug="vera-voice", display_name="Vera Voice",
        visibility=Visibility.public, bio="Ik bouw voice-agents.",
        public_sections=["bio"],  # 'wat ik maak' besloten voor bezoekers
    )
    s.add(p); s.flush()
    s.add(Offering(profile_id=p.id, title="Voicebot Studio", kind=OfferingKind.project,
                   description="Een tool.", slug="voicebot-studio"))
    s.commit()
    ids = {"maker": maker.id, "watcher": watcher.id}
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

    def _factory(member_id):
        def _cm(db: Session = Depends(get_db)):
            return db.get(Member, member_id) if member_id is not None else None
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _cm
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def test_visitor_detail_hides_private_makes(make_client, seed):
    resp = make_client(None).get("/leden/vera-voice")
    assert resp.status_code == 200
    assert "Ik bouw voice-agents." in resp.text   # bio is publiek
    assert "Wat ik maak" not in resp.text          # 'makes' besloten
    assert "Voicebot Studio" not in resp.text      # het project lekt niet


def test_member_detail_sees_everything(make_client, seed):
    resp = make_client(seed["watcher"]).get("/leden/vera-voice")
    assert resp.status_code == 200
    assert "Wat ik maak" in resp.text
    assert "Voicebot Studio" in resp.text


def test_visitor_gids_filter_does_not_surface_private_makes(make_client, seed):
    resp = make_client(None).get("/leden?maakt=Voicebot")
    assert resp.status_code == 200
    assert "Vera Voice" not in resp.text  # niet vindbaar via het besloten werk


def test_member_gids_filter_surfaces_it(make_client, seed):
    resp = make_client(seed["watcher"]).get("/leden?maakt=Voicebot")
    assert resp.status_code == 200
    assert "Vera Voice" in resp.text  # lid ziet alles


def test_visitor_project_deeplink_is_gated(make_client, seed):
    # Bezoeker mag een los project van een besloten-'makes'-profiel niet via de
    # deep-link zien (PRD §6.7) → verborgen (login-redirect voor anon).
    resp = make_client(None).get("/projecten/voicebot-studio", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_member_project_deeplink_visible(make_client, seed):
    resp = make_client(seed["watcher"]).get("/projecten/voicebot-studio")
    assert resp.status_code == 200
    assert "Voicebot Studio" in resp.text


def test_edit_toggle_route_sets_sections(make_client, SessionTest, seed):
    """De oude /profiel/zichtbaarheid-toggle legt nu óók de sectie-keuze vast (parity)."""
    from app.models import Profile, Visibility

    client = make_client(seed["maker"])
    token = csrf_token(client, "/leden")
    resp = client.post(
        "/profiel/zichtbaarheid",
        data={"visibility": "public", "consent": "on", "sections": ["makes", "needs"]},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    s = SessionTest()
    p = s.scalar(select(Profile).where(Profile.slug == "vera-voice"))
    assert p.visibility == Visibility.public
    assert p.public_sections == ["makes", "needs"]  # gesaneerd + vaste volgorde
    s.close()
