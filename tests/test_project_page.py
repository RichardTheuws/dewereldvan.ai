"""Projectdetailpagina (L3) — zichtbaarheidspoort + rename-301 + 404 + noindex.

De poort hangt op het EIGENAAR-profiel: een project van een besloten/geschorst
lid bestaat publiek niet (anon → login, ingelogd-niet-toegestaan → 404). Een
onbekende-maar-historische slug 301't naar de huidige; een echt onbekende → 404.
Noindex spiegelt ``is_noindex`` van de eigenaar.
"""

from __future__ import annotations

import pytest
from app.models import Base, Member, MemberStatus, Offering, Profile, Visibility
from app.services import offering_slug
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Wegwerp-engine + client (current_member instelbaar)                          #
# --------------------------------------------------------------------------- #
@pytest.fixture
def route_engine():
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
def SessionTest(route_engine):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=route_engine, autoflush=False, future=True)


@pytest.fixture
def make_client(route_engine, SessionTest):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app
    from fastapi import Depends
    from sqlalchemy.orm import Session

    def _override_get_db():
        s = SessionTest()
        try:
            yield s
        finally:
            s.close()

    def _factory(member_id: int | None):
        def _override_current_member(db: Session = Depends(get_db)):
            return None if member_id is None else db.get(Member, member_id)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def _seed_project(
    SessionTest, *, visibility: Visibility, owner_status: MemberStatus, title="Het Project"
) -> str:
    """Maak owner+profiel+offering met slug; retourneer de project-slug."""
    s = SessionTest()
    try:
        owner = Member(
            email=f"{visibility.value}-{owner_status.value}@example.com",
            name="Maker",
            status=owner_status,
        )
        s.add(owner)
        s.flush()
        profile = Profile(
            member_id=owner.id,
            slug=f"maker-{visibility.value}-{owner_status.value}",
            display_name="Maker",
            visibility=visibility,
        )
        s.add(profile)
        s.flush()
        off = Offering(profile_id=profile.id, title=title, position=0)
        s.add(off)
        s.flush()
        slug = offering_slug.ensure_slug(s, off)
        s.commit()
        return slug
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Zichtbaarheidspoort                                                         #
# --------------------------------------------------------------------------- #
def test_public_approved_project_visible(make_client, SessionTest):
    slug = _seed_project(
        SessionTest, visibility=Visibility.public, owner_status=MemberStatus.approved
    )
    resp = make_client(None).get(f"/projecten/{slug}")
    assert resp.status_code == 200
    assert "Het Project" in resp.text
    # Publiek → indexeerbaar → geen noindex-meta.
    assert 'name="robots" content="noindex"' not in resp.text


def test_members_only_owner_project_anon_redirects_to_login(make_client, SessionTest):
    slug = _seed_project(
        SessionTest, visibility=Visibility.members, owner_status=MemberStatus.approved
    )
    resp = make_client(None).get(f"/projecten/{slug}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/login")


def test_suspended_owner_project_delisted_for_anon(make_client, SessionTest):
    """Een geschorste eigenaar → project niet publiek leesbaar (anon → login)."""
    slug = _seed_project(
        SessionTest, visibility=Visibility.public, owner_status=MemberStatus.suspended
    )
    resp = make_client(None).get(f"/projecten/{slug}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/login")


def test_suspended_owner_project_is_noindex_for_owner(make_client, SessionTest):
    """De eigenaar ziet z'n eigen project nog wél — maar met noindex (gedelist)."""
    s = SessionTest()
    try:
        owner = Member(
            email="self-susp@example.com", name="Maker", status=MemberStatus.suspended
        )
        s.add(owner)
        s.flush()
        profile = Profile(
            member_id=owner.id,
            slug="self-susp",
            display_name="Maker",
            visibility=Visibility.public,
        )
        s.add(profile)
        s.flush()
        off = Offering(profile_id=profile.id, title="Eigen Project", position=0)
        s.add(off)
        s.flush()
        slug = offering_slug.ensure_slug(s, off)
        s.commit()
        owner_id = owner.id
    finally:
        s.close()
    resp = make_client(owner_id).get(f"/projecten/{slug}")
    assert resp.status_code == 200
    assert 'name="robots" content="noindex"' in resp.text


def test_unknown_slug_is_404(make_client, SessionTest):
    _seed_project(
        SessionTest, visibility=Visibility.public, owner_status=MemberStatus.approved
    )
    resp = make_client(None).get("/projecten/bestaat-echt-niet", follow_redirects=False)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Rename → 301 op de oude slug                                                #
# --------------------------------------------------------------------------- #
def test_renamed_project_old_slug_301s_to_current(make_client, SessionTest):
    # Seed + rename binnen één sessie, en haal de slugs op.
    s = SessionTest()
    try:
        owner = Member(
            email="rename@example.com", name="Hernoemer", status=MemberStatus.approved
        )
        s.add(owner)
        s.flush()
        profile = Profile(
            member_id=owner.id,
            slug="hernoemer",
            display_name="Hernoemer",
            visibility=Visibility.public,
        )
        s.add(profile)
        s.flush()
        off = Offering(profile_id=profile.id, title="Oude Projectnaam", position=0)
        s.add(off)
        s.flush()
        old = offering_slug.ensure_slug(s, off)
        new = offering_slug.rename_to(s, off, "Nieuwe Projectnaam")
        s.commit()
    finally:
        s.close()

    resp = make_client(None).get(f"/projecten/{old}", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == f"/projecten/{new}"
