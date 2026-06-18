"""Route-smoke voor de ledenpagina-feature — alle nieuwe routes + import-smoke.

Bewijst dat de modellen/services/routers/templates importeren en dat de routes
de juiste statuscodes geven: publieke /leden + persoon + project (200),
besloten persoon (303→login, noindex-meta), foto-POST (require_member 303 anon,
CSRF-403 zonder token), emphasis/verwijder-POST's, sitemap/robots (200).
Geen netwerk; foto-upload raakt de echte Pillow-pijplijn op de tmpdir.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from app.models import Base, Member, MemberStatus, Offering, Profile, Visibility
from app.services import offering_slug
from fastapi.testclient import TestClient
from PIL import Image


# --------------------------------------------------------------------------- #
# Import-smoke                                                                #
# --------------------------------------------------------------------------- #
def test_feature_modules_import():
    # Modellen + enum.
    from app.models import OfferingSlugHistory, ProfileEmphasis  # noqa: F401

    # Routers.
    from app.routers import members, photo, projects, seo  # noqa: F401

    # Services.
    from app.services import (  # noqa: F401
        emphasis_service,
        members_service,
        offering_slug,
        photo_service,
        seo_service,
    )
    from app.storage import photos  # noqa: F401


def test_app_mounts_all_feature_routes():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/leden" in paths
    assert "/leden/{slug}" in paths
    assert "/projecten/{slug}" in paths
    assert "/profiel/foto" in paths
    assert "/profiel/foto/verwijderen" in paths
    assert "/profiel/emphasis" in paths
    assert "/sitemap.xml" in paths
    assert "/robots.txt" in paths
    # De StaticFiles-mount voor de geüploade foto's.
    assert any(getattr(r, "name", None) == "uploads" for r in app.routes)


# --------------------------------------------------------------------------- #
# Wegwerp-engine + client (current_member instelbaar)                         #
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


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (300, 300), (30, 90, 180)).save(buf, format="PNG")
    return buf.getvalue()


def _seed(SessionTest):
    """Approved publiek lid + besloten lid + een publiek project. Geeft ids/slugs."""
    s = SessionTest()
    try:
        approved = Member(
            email="approved@example.com", name="Bouwer", status=MemberStatus.approved
        )
        closed = Member(
            email="closed@example.com", name="Besloten", status=MemberStatus.approved
        )
        s.add_all([approved, closed])
        s.flush()
        p_pub = Profile(
            member_id=approved.id,
            slug="bouwer",
            display_name="Bouwer",
            visibility=Visibility.public,
            bio="Korte bio.",
        )
        p_closed = Profile(
            member_id=closed.id,
            slug="besloten",
            display_name="Besloten",
            visibility=Visibility.members,
        )
        s.add_all([p_pub, p_closed])
        s.flush()
        off = Offering(profile_id=p_pub.id, title="Publiek Project", position=0)
        s.add(off)
        s.flush()
        proj_slug = offering_slug.ensure_slug(s, off)
        s.commit()
        return {
            "approved": approved.id,
            "pub_slug": p_pub.slug,
            "closed_slug": p_closed.slug,
            "proj_slug": proj_slug,
        }
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Publieke GET-routes                                                         #
# --------------------------------------------------------------------------- #
def test_leden_overview_200(make_client, SessionTest):
    _seed(SessionTest)
    assert make_client(None).get("/leden").status_code == 200


def test_public_person_200(make_client, SessionTest):
    ids = _seed(SessionTest)
    resp = make_client(None).get(f"/leden/{ids['pub_slug']}")
    assert resp.status_code == 200
    assert "Bouwer" in resp.text


def test_closed_person_anon_303_to_login(make_client, SessionTest):
    ids = _seed(SessionTest)
    resp = make_client(None).get(
        f"/leden/{ids['closed_slug']}", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/login")


def test_closed_person_owner_sees_noindex(make_client, SessionTest):
    from sqlalchemy import select

    ids = _seed(SessionTest)
    # De eigenaar van het besloten profiel ziet de pagina mét noindex-meta.
    s = SessionTest()
    try:
        owner = s.scalar(
            select(Profile).where(Profile.slug == ids["closed_slug"])
        )
        owner_id = owner.member_id
    finally:
        s.close()
    resp = make_client(owner_id).get(f"/leden/{ids['closed_slug']}")
    assert resp.status_code == 200
    assert 'name="robots" content="noindex"' in resp.text


def test_public_project_200(make_client, SessionTest):
    ids = _seed(SessionTest)
    resp = make_client(None).get(f"/projecten/{ids['proj_slug']}")
    assert resp.status_code == 200


def test_unknown_person_404(make_client, SessionTest):
    _seed(SessionTest)
    resp = make_client(None).get("/leden/niemand", follow_redirects=False)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST-routes — require_member + CSRF                                         #
# --------------------------------------------------------------------------- #
def test_photo_upload_anonymous_redirects_to_login(make_client, SessionTest):
    """Anon mét geldige CSRF-token: require_member stuurt naar /login (303).

    De CSRF-token wordt eerst gemint via een anonieme GET (/login), zodat we
    voorbij de CSRF-middleware komen en juist de require_member-poort raken.
    """
    import re

    _seed(SessionTest)
    client = make_client(None)
    page = client.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    resp = client.post(
        "/profiel/foto",
        files={"file": ("x.png", _png(), "image/png")},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


def test_photo_upload_without_csrf_is_403(make_client, SessionTest):
    ids = _seed(SessionTest)
    resp = make_client(ids["approved"]).post(
        "/profiel/foto",
        files={"file": ("x.png", _png(), "image/png")},
    )
    assert resp.status_code == 403


def test_emphasis_post_without_csrf_is_403(make_client, SessionTest):
    ids = _seed(SessionTest)
    resp = make_client(ids["approved"]).post(
        "/profiel/emphasis", data={"emphasis": "person"}
    )
    assert resp.status_code == 403


def test_photo_delete_without_csrf_is_403(make_client, SessionTest):
    ids = _seed(SessionTest)
    resp = make_client(ids["approved"]).post("/profiel/foto/verwijderen")
    assert resp.status_code == 403


def _csrf(client: TestClient) -> str:
    """Mint de session-CSRF-token via de bewerkpagina en haal 'm uit hx-headers."""
    import re

    page = client.get("/profiel/bewerken")
    assert page.status_code == 200
    m = re.search(r"X-CSRF-Token&#34;: &#34;([^&]+)&#34;", page.text) or re.search(
        r'name="csrf_token" value="([^"]+)"', page.text
    )
    assert m, "CSRF-token niet gevonden op de bewerkpagina"
    return m.group(1)


def test_photo_upload_with_csrf_succeeds(make_client, SessionTest):
    ids = _seed(SessionTest)
    client = make_client(ids["approved"])
    token = _csrf(client)
    resp = client.post(
        "/profiel/foto",
        files={"file": ("foto.png", _png(), "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200


def test_emphasis_with_csrf_persists(make_client, SessionTest):
    ids = _seed(SessionTest)
    client = make_client(ids["approved"])
    token = _csrf(client)
    resp = client.post(
        "/profiel/emphasis",
        data={"emphasis": "projects"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    # Persistentie controleren in de DB.
    from app.models import ProfileEmphasis
    from sqlalchemy import select

    s = SessionTest()
    try:
        prof = s.scalar(
            select(Profile).where(Profile.member_id == ids["approved"])
        )
        assert prof.emphasis is ProfileEmphasis.projects
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# SEO-routes                                                                  #
# --------------------------------------------------------------------------- #
def test_sitemap_and_robots_200(make_client, SessionTest):
    _seed(SessionTest)
    client = make_client(None)
    assert client.get("/sitemap.xml").status_code == 200
    assert client.get("/robots.txt").status_code == 200
