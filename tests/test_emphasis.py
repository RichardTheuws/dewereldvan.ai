"""Emphasis (L1) — enum-default + set_emphasis + layout-class in de render.

Bewijst dat ``profile.emphasis`` default ``balanced`` is, dat ``set_emphasis``
normaliseert/persisteert, en dat de gerenderde profielpagina de juiste
``emphasis-*``-class draagt (de layout-sturing zit puur in de class, geen JS).
"""

from __future__ import annotations

import pytest
from app.models import Base, ProfileEmphasis, Visibility
from app.services import emphasis_service
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Service-laag                                                                 #
# --------------------------------------------------------------------------- #
def test_new_profile_defaults_to_balanced(db, make_member, make_profile):
    member = make_member(email="bal@example.com")
    profile = make_profile(member)  # geen emphasis meegegeven
    assert profile.emphasis is ProfileEmphasis.balanced


def test_parse_emphasis_normalizes_and_falls_back():
    assert emphasis_service.parse_emphasis("person") is ProfileEmphasis.person
    assert emphasis_service.parse_emphasis("PROJECTS") is ProfileEmphasis.projects
    # Onbekend/leeg → veilige fallback naar balanced.
    assert emphasis_service.parse_emphasis("bogus") is ProfileEmphasis.balanced
    assert emphasis_service.parse_emphasis(None) is ProfileEmphasis.balanced


def test_set_emphasis_persists(db, make_member, make_profile):
    member = make_member(email="set@example.com")
    profile = make_profile(member)
    out = emphasis_service.set_emphasis(db, profile, "person")
    assert out is ProfileEmphasis.person
    assert profile.emphasis is ProfileEmphasis.person


def test_emphasis_class_mapping(db, make_member, make_profile):
    member = make_member(email="cls@example.com")
    profile = make_profile(member, emphasis=ProfileEmphasis.projects)
    assert emphasis_service.emphasis_class(profile) == "emphasis-projects"


# --------------------------------------------------------------------------- #
# Render — de class belandt op de pagina (layout-sturing)                      #
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


def _seed_public_profile(page_engine, *, emphasis: ProfileEmphasis):
    from app.models import Member, MemberStatus, Profile
    from sqlalchemy.orm import Session

    with Session(page_engine) as s:
        m = Member(
            email=f"{emphasis.value}@example.com",
            name=f"Lid {emphasis.value}",
            status=MemberStatus.approved,
        )
        s.add(m)
        s.flush()
        p = Profile(
            member_id=m.id,
            slug=f"lid-{emphasis.value}",
            display_name=f"Lid {emphasis.value}",
            visibility=Visibility.public,
            emphasis=emphasis,
            bio="Een korte bio.",
        )
        s.add(p)
        s.commit()
        return p.slug


@pytest.mark.parametrize(
    "emphasis",
    [ProfileEmphasis.person, ProfileEmphasis.projects, ProfileEmphasis.balanced],
)
def test_profile_page_renders_emphasis_class(client, page_engine, emphasis):
    slug = _seed_public_profile(page_engine, emphasis=emphasis)
    resp = client.get(f"/leden/{slug}")
    assert resp.status_code == 200
    assert f"emphasis-{emphasis.value}" in resp.text
