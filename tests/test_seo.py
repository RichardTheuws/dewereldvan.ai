"""SEO-laag (L4) — sitemap-poort, JSON-LD-shape, robots.

- ``sitemap_entries`` bevat publieke personen + projecten en SLUIT
  besloten/geschorst uit (dezelfde poort als ``can_view(anon)``).
- ``jsonld_person`` / ``jsonld_project`` hebben de verplichte schema.org-keys.
- ``/sitemap.xml`` serveert ``application/xml``; ``/robots.txt`` verwijst naar de
  sitemap en disallowt de besloten/ingelogde paden.
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
from app.services import offering_slug, seo_service
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# sitemap_entries — poort (besloten/geschorst uitgesloten)                     #
# --------------------------------------------------------------------------- #
def test_sitemap_includes_public_excludes_closed_and_suspended(
    db, make_member, make_profile, make_offering
):
    pub = make_member(email="pub@example.com", name="Publiek")
    p_pub = make_profile(pub, visibility=Visibility.public)
    off = make_offering(p_pub, title="Open Project")
    offering_slug.ensure_slug(db, off)

    closed = make_member(email="closed@example.com", name="Besloten")
    make_profile(closed, visibility=Visibility.members)

    susp = make_member(
        email="susp@example.com", name="Geschorst", status=MemberStatus.suspended
    )
    make_profile(susp, visibility=Visibility.public)

    locs = {e.loc for e in seo_service.sitemap_entries(db)}
    assert any(loc.endswith("/leden/" + p_pub.slug) for loc in locs)
    assert any(loc.endswith("/projecten/" + off.slug) for loc in locs)
    # Besloten/geschorst personen mogen NIET in de sitemap staan.
    assert not any("besloten" in loc.lower() for loc in locs)
    assert not any("/leden/geschorst" in loc for loc in locs)


def test_sitemap_skips_offerings_without_slug(db, make_member, make_profile, make_offering):
    pub = make_member(email="noslug@example.com", name="Publiek")
    p = make_profile(pub, visibility=Visibility.public)
    make_offering(p, title="Slug-loos")  # bewust GEEN ensure_slug
    locs = {e.loc for e in seo_service.sitemap_entries(db)}
    # De persoon staat erin, maar het slug-loze project niet.
    assert any(loc.endswith("/leden/" + p.slug) for loc in locs)
    assert not any("/projecten/" in loc for loc in locs)


def test_sitemap_excludes_projects_when_makes_section_is_private(
    db, make_member, make_profile, make_offering
):
    """Een publiek profiel dat 'wat ik maak' besloten houdt (``makes`` niet in
    ``public_sections``): de persoon blijft in de sitemap, maar z'n project-URLs
    lekken er niet in (spiegelt de members-gate op /projecten/{slug})."""
    m = make_member(email="privmakes@example.com", name="Priv Makes")
    p = make_profile(m, visibility=Visibility.public)
    p.public_sections = ["bio"]  # 'makes' bewust NIET publiek
    off = make_offering(p, title="Verborgen Project")
    offering_slug.ensure_slug(db, off)
    db.flush()

    locs = {e.loc for e in seo_service.sitemap_entries(db)}
    # De persoon (basiskaart) blijft indexeerbaar...
    assert any(loc.endswith("/leden/" + p.slug) for loc in locs)
    # ...maar het project van de besloten 'makes'-sectie niet.
    assert not any(loc.endswith("/projecten/" + off.slug) for loc in locs)


def test_sitemap_includes_projects_when_makes_section_public(
    db, make_member, make_profile, make_offering
):
    """Controle-tak: staat 'makes' wél publiek, dan hoort het project er gewoon in."""
    m = make_member(email="pubmakes@example.com", name="Pub Makes")
    p = make_profile(m, visibility=Visibility.public)
    p.public_sections = ["makes"]
    off = make_offering(p, title="Zichtbaar Project")
    offering_slug.ensure_slug(db, off)
    db.flush()

    locs = {e.loc for e in seo_service.sitemap_entries(db)}
    assert any(loc.endswith("/projecten/" + off.slug) for loc in locs)


# --------------------------------------------------------------------------- #
# JSON-LD shapes                                                              #
# --------------------------------------------------------------------------- #
def test_jsonld_person_shape(db, make_member, make_profile):
    m = make_member(email="ld@example.com", name="Sterre Licht")
    p = make_profile(
        m, visibility=Visibility.public, headline="Bouwt zorgtech", bio="Lange bio"
    )
    tag = Tag(name="Zorg", slug="zorg")
    db.add(tag)
    db.flush()
    p.tags = [tag]
    db.flush()

    data = seo_service.jsonld_person(p)
    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "Person"
    assert data["name"] == "Sterre Licht"
    assert data["url"].endswith("/leden/" + p.slug)
    assert data["description"] == "Bouwt zorgtech"  # headline wint van bio
    assert data["knowsAbout"] == ["Zorg"]


def test_jsonld_project_software_when_external_url(db, make_member, make_profile, make_offering):
    m = make_member(email="proj@example.com", name="Maker")
    p = make_profile(m, visibility=Visibility.public)
    off = make_offering(
        p, title="Mijn App", description="Doet iets", url="https://app.example.com"
    )
    offering_slug.ensure_slug(db, off)

    data = seo_service.jsonld_project(off)
    assert data["@type"] == "SoftwareApplication"
    assert data["name"] == "Mijn App"
    assert data["url"] == "https://app.example.com"  # externe site
    assert data["author"]["@type"] == "Person"
    assert data["author"]["url"].endswith("/leden/" + p.slug)


def test_jsonld_project_creativework_without_external_url(
    db, make_member, make_profile, make_offering
):
    m = make_member(email="cw@example.com", name="Maker")
    p = make_profile(m, visibility=Visibility.public)
    off = make_offering(p, title="Geen Link Project")
    offering_slug.ensure_slug(db, off)

    data = seo_service.jsonld_project(off)
    assert data["@type"] == "CreativeWork"
    assert data["url"].endswith("/projecten/" + off.slug)


def test_absolute_url_makes_relative_uploads_absolute():
    out = seo_service.absolute_url("/uploads/face.webp")
    assert out is not None
    assert out.endswith("/uploads/face.webp")
    assert out.startswith("http")
    # Al-absolute blijft ongemoeid.
    assert (
        seo_service.absolute_url("https://cdn.example.com/x.png")
        == "https://cdn.example.com/x.png"
    )


# --------------------------------------------------------------------------- #
# HTTP — /sitemap.xml + /robots.txt                                          #
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


def test_sitemap_route_serves_xml_with_public_only(client, page_engine):
    from sqlalchemy.orm import Session

    with Session(page_engine) as s:
        pub = Member(email="p@example.com", name="Pub", status=MemberStatus.approved)
        closed = Member(
            email="c@example.com", name="Closed", status=MemberStatus.approved
        )
        s.add_all([pub, closed])
        s.flush()
        s.add_all(
            [
                Profile(
                    member_id=pub.id,
                    slug="pub-lid",
                    display_name="Pub",
                    visibility=Visibility.public,
                    headline="Bouwt met AI",
                ),
                Profile(
                    member_id=closed.id,
                    slug="closed-lid",
                    display_name="Closed",
                    visibility=Visibility.members,
                ),
            ]
        )
        s.commit()

    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "/leden/pub-lid" in resp.text
    assert "/leden/closed-lid" not in resp.text


def test_robots_route(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "Sitemap:" in resp.text
    assert "Disallow: /admin/" in resp.text
    assert "Disallow: /login" in resp.text
    # De besloten profielen zitten op /leden/{slug} en zijn per-pagina noindex
    # (de echte poort); robots disallowt geen niet-bestaande /profiel/-route meer.
    assert "Disallow: /profiel/" not in resp.text


# --------------------------------------------------------------------------- #
# /gek-genoeg — publieke presentatie over de intelligentie-explosie            #
# --------------------------------------------------------------------------- #
def test_gek_genoeg_is_public_and_shareable(client):
    resp = client.get("/gek-genoeg")
    assert resp.status_code == 200
    html = resp.text
    assert "Doe maar gewoon," in html and "dan doe je al" in html
    assert html.count('class="scene') == 15
    # Deelbaar: canonical, eigen deelbeeld en geen noindex.
    assert '<link rel="canonical" href="https://' in html
    assert 'property="og:image"' in html and "/static/og-gek-genoeg-3d.png" in html
    assert 'name="robots" content="noindex"' not in html
    # Transparant over de herkomst (AI-axioma) en met bronnen.
    assert "Frank Meeuwsen" in html and "Gemaakt met Claude" in html
    # De prompt is van een onbekende schrijver; Frank stuurde hem alleen door.
    assert "Eoin McKenna" in html and "schrijver van de prompt kennen we niet" in html
    assert "metr.org/time-horizons" in html


def test_gek_genoeg_counts_only_public_makers(client, page_engine):
    """Het makers-getal volgt de gids-poort: besloten profielen tellen niet mee
    en er staat geen enkele naam op de pagina."""
    from sqlalchemy.orm import Session

    with Session(page_engine) as s:
        pub = Member(email="gg-p@example.com", name="Zichtbaar", status=MemberStatus.approved)
        closed = Member(email="gg-c@example.com", name="Verborgen", status=MemberStatus.approved)
        s.add_all([pub, closed])
        s.flush()
        s.add_all(
            [
                Profile(
                    member_id=pub.id,
                    slug="gg-pub",
                    display_name="Zichtbaar Lid",
                    visibility=Visibility.public,
                    headline="Bouwt met AI",
                ),
                Profile(
                    member_id=closed.id,
                    slug="gg-closed",
                    display_name="Verborgen Lid",
                    visibility=Visibility.members,
                    headline="Bouwt ook met AI",
                ),
            ]
        )
        s.commit()

    html = client.get("/gek-genoeg").text
    assert 'data-makers="1"' in html
    assert "Zichtbaar Lid" not in html and "Verborgen Lid" not in html


def test_gek_genoeg_in_sitemap(client):
    assert "/gek-genoeg" in client.get("/sitemap.xml").text


def test_gek_genoeg_follows_styleguide():
    """STYLEGUIDE §8: geen gedachtestreepjes in eigen copy, geen glyph-iconen; en
    geen data-reveal (de pagina includet de reveal-director niet)."""
    from pathlib import Path

    src = Path("app/templates/gek_genoeg.html").read_text(encoding="utf-8")
    assert "—" not in src and "✦" not in src
    assert "data-reveal" not in src
    assert "prefers-reduced-motion" in src


def test_gek_genoeg_3d_engine_is_self_hosted(client):
    """De 3D-werelden draaien op een zelf gehoste three.js met de versie in de
    bestandsnaam (statics zijn immutable gecachet), en de bediening werkt los van
    WebGL: het UI-script staat apart van de module."""
    html = client.get("/gek-genoeg").text
    assert 'from "/static/vendor/three-0.170.0.module.min.js"' in html
    assert html.count('<script type="module">') == 1 and "window.GG" in html
    assert "cdn.jsdelivr.net" not in html and "unpkg.com" not in html
    lib = client.get("/static/vendor/three-0.170.0.module.min.js")
    assert lib.status_code == 200 and "SPDX-License-Identifier: MIT" in lib.text[:200]
    # De nieuwste METR-meting staat met bron en marge op de pagina.
    assert "2026-11-20-q4-2026-capability-update" in html and "13 tot 2.645 uur" in html


def test_gek_genoeg_story_order(client):
    """De verhaallijn: meten, wat het voor jou betekent, waarom het doorloopt, de
    eerlijke kant, bouwen, en pas dan hoe deze pagina zelf begon."""
    import re

    order = re.findall(r'<section class="scene[^>]*data-id="(\w+)"', client.get("/gek-genoeg").text)
    assert order == [
        "gewoon", "tulp", "mijlpalen", "lijn", "vouwen", "jij", "lus", "veldhoven",
        "kopie", "eeuw", "eerlijk", "water", "doen", "prompt", "slot",
    ]


def test_gek_genoeg_opening_and_prompt_world(client):
    """De opening houdt de tweede helft van de kop even achter (class `late`), maar
    nooit bij verminderde beweging of zonder JavaScript. De prompt-wereld typt de
    echte prompt uit het bronnenpaneel, dus die alinea moet vindbaar blijven."""
    html = client.get("/gek-genoeg").text
    assert '<span class="late" id="late">dan doe je al' in html
    assert ".late,.scene.on .late{opacity:1;animation:none}" in html
    assert ".late{opacity:1;animation:none}</style></noscript>" in html
    assert 'id="prompt-src">"make a presentation on the future of AI' in html
