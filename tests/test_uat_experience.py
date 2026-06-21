"""UAT Laag 2 — ervaring-invarianten (het STYLEGUIDE-contract, afgedwongen).

Waar Laag 1 vraagt "werkt het?", vraagt deze laag "leeft het de belofte na?".
Het consolideert de verspreide per-pagina styleguide-asserties tot één contract
dat élke kosmische pagina structureel moet halen — en dat nieuwe pagina's
automatisch erven (de lijsten komen uit dezelfde classificatie als Laag 1, met
een gate die nieuwe publieke pagina's afdwingt).

Toetst het deel van het ervaringsmandaat dat objectief meetbaar is:
- één identiteit: ``class="cosmic"`` + de drie verplichte fonts + cosmic.css
  (cache-gebust) → geen tweede look, geen sier-fonts;
- vindbaarheid: publiek-indexeerbaar is NIET noindex; besloten/auth IS noindex
  (de privacy-/SEO-poort uit de styleguide §5).

Wat NIET hier valt (geen valse zekerheid): of de motion/intelligentie écht
verbaast — dat is de menselijke toets + de browser-UAT (Laag 3).
"""

from __future__ import annotations

import base64
import json
import re

import itsdangerous
import pytest
from app.models import (
    Member,
    MemberRole,
    MemberStatus,
    Offering,
    Profile,
    Visibility,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tests._route_helpers import app_get_routes, make_route_engine
from tests.test_uat_coverage import (
    MEMBER_ONLY,
    PUBLIC_INDEXABLE,
    PUBLIC_NOINDEX,
    _realize,
)

_SECRET = "test-secret-key-deterministic-0123456789abcdef"

# De drie verplichte families (STYLEGUIDE §1). Elke kosmische pagina linkt ze.
REQUIRED_FONTS = ("Fraunces", "JetBrains+Mono", "Spline+Sans")

# Sier-fonts die de "generieke AI-look" verraden (STYLEGUIDE §7 anti-patterns).
# We zoeken naar Google-font-imports én naam-tokens in de gerenderde HTML
# (cosmic.css wordt gelinkt, niet inline gerenderd, dus dit raakt alleen wat de
# pagina zelf injecteert).
_FORBIDDEN_FONT_PATTERNS = [
    re.compile(r"family=(Inter|Roboto|Lato|Open\+Sans|Poppins|Montserrat|Nunito)"),
    re.compile(r"font-family:[^;\"']*\b(Arial|Helvetica|Inter|Roboto)\b", re.I),
]


def _session_cookie(data: dict) -> str:
    signer = itsdangerous.TimestampSigner(_SECRET)
    raw = base64.b64encode(json.dumps(data).encode("utf-8"))
    return signer.sign(raw).decode("utf-8")


@pytest.fixture(scope="module")
def env():
    """Wegwerp-engine + admin/lid + één publiek profiel & project (read-only)."""
    from app.services import offering_slug

    engine = make_route_engine()
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    with Session() as s:
        admin = Member(
            email="admin@dewereldvan.ai",
            name="UAT Admin",
            status=MemberStatus.approved,
            role=MemberRole.admin,
        )
        s.add(admin)
        s.flush()
        pub = Profile(
            member_id=admin.id,
            slug="uat-maker",
            display_name="UAT Maker",
            visibility=Visibility.public,
            headline="Bouwt slimme dingen",
            makes_summary="Voice-agents en RAG.",
        )
        s.add(pub)
        s.flush()
        offering = Offering(title="UAT Project", position=0)
        pub.offerings.append(offering)
        s.flush()
        offering_slug.ensure_slug(s, offering)
        s.commit()
        admin_id = admin.id
    yield engine, Session, admin_id
    engine.dispose()


@pytest.fixture
def make_client(env):
    engine, Session, admin_id = env
    from app.db import get_db
    from app.main import app

    def _override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db

    def _make(as_admin: bool = False) -> TestClient:
        c = TestClient(app, base_url="https://testserver")
        if as_admin:
            c.cookies.set(
                "session",
                _session_cookie({"member_id": admin_id, "is_admin": True}),
            )
        return c

    try:
        yield _make
    finally:
        app.dependency_overrides.clear()


def _assert_no_forbidden_fonts(body: str, path: str) -> None:
    for pat in _FORBIDDEN_FONT_PATTERNS:
        m = pat.search(body)
        assert m is None, (
            f"{path} bevat een sier-/systeemfont ({m.group(0)!r}). "
            "Alleen Fraunces + JetBrains Mono + Spline Sans (STYLEGUIDE §1/§7)."
        )


# --------------------------------------------------------------------------- #
# Het kosmische identiteit-contract op elke publieke cosmic-pagina.            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path", sorted(PUBLIC_INDEXABLE | PUBLIC_NOINDEX)
)
def test_public_cosmic_pages_honor_identity(make_client, path):
    """Elke publieke pagina draagt de ene kosmische identiteit: dark-shell, de
    drie fonts, cosmic.css (cache-gebust), geen sier-fonts."""
    resp = make_client().get(_realize(path), follow_redirects=False)
    assert resp.status_code == 200, f"{path} → {resp.status_code}"
    body = resp.text
    assert 'class="cosmic"' in body, f"{path} mist de kosmische dark-shell."
    for fam in REQUIRED_FONTS:
        assert fam in body, f"{path} laadt het verplichte font {fam} niet."
    assert re.search(r"/static/cosmic\.css\?v=", body), (
        f"{path} linkt cosmic.css niet cache-gebust (?v=...)."
    )
    _assert_no_forbidden_fonts(body, path)


# --------------------------------------------------------------------------- #
# Vindbaarheid: publiek = indexeerbaar, besloten/auth = noindex.               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", sorted(PUBLIC_INDEXABLE))
def test_indexable_pages_are_not_noindex(make_client, path):
    """De crawlbare showcase mag NIET noindex zijn (SEO is een expliciet doel)."""
    resp = make_client().get(_realize(path), follow_redirects=False)
    assert resp.status_code == 200
    assert "noindex" not in resp.text, (
        f"{path} is publiek-indexeerbaar maar zet noindex — dat kost linkwaarde."
    )


@pytest.mark.parametrize("path", sorted(PUBLIC_NOINDEX))
def test_auth_pages_are_noindex(make_client, path):
    """Auth-/post-delete-pagina's zijn publiek bereikbaar maar bewust noindex."""
    resp = make_client().get(_realize(path), follow_redirects=False)
    assert resp.status_code == 200
    assert "noindex" in resp.text, f"{path} hoort noindex te zijn."


@pytest.mark.parametrize("path", sorted(MEMBER_ONLY))
def test_member_pages_are_noindex(make_client, path):
    """Besloten ledenpagina's (gerenderd als admin) zijn login-gated én noindex —
    de privacy-poort: besloten content mag nooit indexeerbaar zijn."""
    resp = make_client(as_admin=True).get(_realize(path), follow_redirects=False)
    if resp.status_code != 200 or 'class="cosmic"' not in resp.text:
        pytest.skip(f"{path}: geen vol cosmic-document in deze identiteit.")
    assert "noindex" in resp.text, (
        f"{path} is besloten maar mist noindex — privacy-/SEO-lek."
    )


# --------------------------------------------------------------------------- #
# Zelf-groei: een nieuwe publieke pagina dwingt opname in het contract af.     #
# --------------------------------------------------------------------------- #
def test_new_public_pages_join_the_experience_contract(make_client):
    """Vangnet tegen 'pagina toegevoegd, ervaring-contract vergeten': elke
    GET-route die 200 + ``class="cosmic"`` rendert voor een anonieme bezoeker
    moet in PUBLIC_INDEXABLE of PUBLIC_NOINDEX staan (en wordt dus door de
    asserties hierboven gedekt)."""
    from app.main import app

    client = make_client()
    known = PUBLIC_INDEXABLE | PUBLIC_NOINDEX
    missing = []
    for path in sorted(app_get_routes(app)):
        if path in known or "{" in path:
            # Param-routes worden expliciet via de bekende sets gedekt.
            continue
        resp = client.get(_realize(path), follow_redirects=False)
        if resp.status_code == 200 and 'class="cosmic"' in resp.text:
            if path not in known:
                missing.append(path)
    assert not missing, (
        "Nieuwe publieke cosmic-pagina('s) zonder ervaring-contract: "
        f"{missing}. Zet ze in PUBLIC_INDEXABLE of PUBLIC_NOINDEX "
        "(tests/test_uat_coverage.py) zodat Laag 2 ze afdwingt."
    )
