"""UAT Laag 1 — zelf-groeiende route-dekkingswacht.

Doel: "weet altijd zeker dat álles werkt, ook terwijl we doorbouwen." Deze suite
enumereert via ``app_get_routes`` ELKE GET-route live en dwingt drie dingen af:

1. **Geen 5xx, in geen enkele identiteit** — elke GET-route wordt geraakt als
   anoniem, als gewoon lid en als admin; een 500 = een echte bug die hier valt
   (de SSE-streams uitgezonderd: die kan TestClient niet driven, dat is Laag 3).
2. **De auth-poorten kloppen** — publiek-indexeerbare pagina's renderen 200 voor
   anon, leden-pagina's redirecten anon naar /login, admin-pagina's geven 403
   voor een gewoon lid.
3. **Volledigheids-gate (de zelf-groei)** — élke GET-route moet in precies één
   classificatie-bucket zitten. Voeg je een nieuwe pagina toe en classificeer je
   'm niet, dan FAALT ``test_route_inventory_is_acknowledged`` met een duidelijke
   melding. Zo kan geen scherm ongetest/ongeclassificeerd shippen.

Hermetisch: in-memory SQLite, e-mail-backend uit conftest, geen netwerk.
"""

from __future__ import annotations

import base64
import json

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

# Móet matchen met de SECRET_KEY die conftest vóór de app-import zet.
_SECRET = "test-secret-key-deterministic-0123456789abcdef"


def _session_cookie(data: dict) -> str:
    """Teken een sessie-cookie exact zoals Starlette's SessionMiddleware."""
    signer = itsdangerous.TimestampSigner(_SECRET)
    raw = base64.b64encode(json.dumps(data).encode("utf-8"))
    return signer.sign(raw).decode("utf-8")


# --------------------------------------------------------------------------- #
# Route-classificatie — de enige plek die je raakt bij een nieuwe pagina.      #
# --------------------------------------------------------------------------- #
# Publieke, crawlbare showcase (anon → 200, NIET noindex). De launch-surfaces.
PUBLIC_INDEXABLE = {
    "/",
    "/demo",
    "/leden",
    "/leden/{slug}",
    "/projecten/{slug}",
    "/proef",
    # Publieke community-content: anon mag lezen (toevoegen blijft login-gated).
    "/agenda",
    "/nieuws",
}
# Publiek bereikbaar (anon → 200) maar bewust noindex (auth + post-delete).
PUBLIC_NOINDEX = {
    "/register",
    "/login",
    "/profiel/gewist",
}
# Publieke htmx-partials/overlay-fragmenten (concierge zit op elke pagina, ook
# anoniem; anonieme feedback mag). Geen volledige documenten.
PUBLIC_FRAGMENTS = {
    "/concierge/chips",
    "/concierge/index",
    "/concierge/nudge",
    "/feedback/paneel",
}
# Besloten: anon → 303 naar /login. Lid → 200/2xx.
MEMBER_ONLY = {
    "/ideeen",
    "/ideeen/lijkt-op",
    "/roadmap",
    "/welkom",
    "/profiel/voorbeeld",
    "/profiel/bewerken",
    "/profiel/notificaties",
    "/profiel/verbind",
    "/profiel/ai/bouwen",
    "/profiel/ai/veld/{naam}",
    "/profiel/ai/veld/{naam}/bewerken",
    "/profiel/ai/offering/{offering_id}",
    "/profiel/ai/offering/{offering_id}/bewerken",
    "/profiel/ai/rol/{role_id}",
    "/profiel/ai/rol/{role_id}/bewerken",
    "/profiel/ai/ontdek/resultaat",
    "/concierge/profielbouw",
    "/intro/nieuw",
}
# Admin-only: gewoon lid → 403.
ADMIN_ONLY = {
    "/admin/queue",
    "/admin/feedback",
    "/admin/nieuws",
    "/admin/agenda",
    "/admin/roadmap",
    "/admin/uitnodiging",
}
# Infra / niet-cosmic (geen ervarings-contract).
INFRA = {
    "/healthz",
    "/openapi.json",
    "/robots.txt",
    "/sitemap.xml",
}
# Token-gated: zonder geldig token een nette 4xx (geen 5xx).
TOKEN_ROUTES = {
    "/auth/verify",
    "/uitnodiging/{token}",
}
# SSE-streams: TestClient kan een server-sent-events-generator niet zinvol
# uitlezen (de body streamt lui). Uitgezonderd van de no-5xx-probe; de echte
# werking valt onder de browser-UAT (Laag 3).
STREAMING = {
    "/concierge/stream",
    "/profiel/ai/stream",
    "/profiel/ai/ontdek/stream",
}

# Alle geclassificeerde routes (de zelf-groei-gate vergelijkt hiertegen).
ACKNOWLEDGED = (
    PUBLIC_INDEXABLE
    | PUBLIC_NOINDEX
    | PUBLIC_FRAGMENTS
    | MEMBER_ONLY
    | ADMIN_ONLY
    | INFRA
    | TOKEN_ROUTES
    | STREAMING
)

# Padparameter-invulling. Onbekende ids → een waarde die een nette 404/redirect
# geeft (nooit een 500). Bekende slugs verwijzen naar de geseede fixtures.
_PARAM_FILL = {
    "{slug}": "uat-maker",  # default; /projecten/{slug} wordt apart ingevuld
    "{offering_id}": "999999",
    "{role_id}": "999999",
    "{naam}": "bio",
    "{token}": "ongeldige-token",
}


def _realize(path: str) -> str:
    """Vul padparameters in met test-veilige waarden."""
    if path == "/projecten/{slug}":
        return "/projecten/uat-project"
    out = path
    for key, val in _PARAM_FILL.items():
        out = out.replace(key, val)
    return out


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def seeded():
    """Een wegwerp-engine met admin + gewoon lid + één publiek profiel/project.

    Module-scoped: de identiteiten/slugs zijn read-only voor de route-probes, dus
    één seed volstaat voor de hele suite (snel, geen per-test-overhead)."""
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
        member = Member(
            email="lid@uat.example",
            name="UAT Lid",
            status=MemberStatus.approved,
            role=MemberRole.member,
        )
        s.add_all([admin, member])
        s.flush()
        pub = Profile(
            member_id=member.id,
            slug="uat-maker",
            display_name="UAT Maker",
            visibility=Visibility.public,
            headline="Bouwt slimme dingen",
            makes_summary="Voice-agents en RAG-pipelines.",
        )
        s.add(pub)
        s.flush()
        offering = Offering(title="UAT Project", position=0)
        pub.offerings.append(offering)
        s.flush()
        offering_slug.ensure_slug(s, offering)
        s.commit()
        ids = {"admin_id": admin.id, "member_id": member.id}
    yield engine, Session, ids
    engine.dispose()


@pytest.fixture
def make_client(seeded):
    """Factory: een TestClient in een gekozen identiteit (None/lid/admin)."""
    engine, Session, ids = seeded
    from app.db import get_db
    from app.main import app

    def _override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    clients: list[TestClient] = []

    def _make(identity: str | None = None) -> TestClient:
        c = TestClient(app, base_url="https://testserver")
        if identity == "admin":
            c.cookies.set(
                "session",
                _session_cookie({"member_id": ids["admin_id"], "is_admin": True}),
            )
        elif identity == "member":
            c.cookies.set(
                "session", _session_cookie({"member_id": ids["member_id"]})
            )
        clients.append(c)
        return c

    try:
        yield _make
    finally:
        app.dependency_overrides.clear()


def _all_get_routes() -> list[str]:
    from app.main import app

    return sorted(app_get_routes(app))


# --------------------------------------------------------------------------- #
# 1. Geen enkele GET-route mag 5xx geven — in geen enkele identiteit.          #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("identity", [None, "member", "admin"])
@pytest.mark.parametrize("path", _all_get_routes())
def test_no_get_route_errors(make_client, path, identity):
    """De hardste, breedste vangnet-assertie: raak elke GET-route in elke
    identiteit en eis dat 'm nooit 5xx geeft. Een 500 hier = een echte bug."""
    if path in STREAMING:
        pytest.skip("SSE-stream — niet door TestClient te driven (zie Laag 3).")
    client = make_client(identity)
    resp = client.get(_realize(path), follow_redirects=False)
    assert resp.status_code < 500, (
        f"{path} ({identity or 'anon'}) gaf {resp.status_code} "
        f"(server-fout). Een GET-route mag nooit 5xx geven."
    )


# --------------------------------------------------------------------------- #
# 2. Auth-poorten kloppen.                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", sorted(PUBLIC_INDEXABLE))
def test_public_pages_render_for_anonymous(make_client, path):
    """De crawlbare showcase rendert 200 voor een anonieme bezoeker."""
    resp = make_client(None).get(_realize(path), follow_redirects=False)
    assert resp.status_code == 200, f"{path} anon → {resp.status_code} (verwacht 200)"


@pytest.mark.parametrize("path", sorted(MEMBER_ONLY))
def test_member_pages_redirect_anonymous_to_login(make_client, path):
    """Besloten pagina's sturen een anonieme bezoeker naar /login (303)."""
    resp = make_client(None).get(_realize(path), follow_redirects=False)
    assert resp.status_code == 303, f"{path} anon → {resp.status_code} (verwacht 303)"
    assert resp.headers.get("location", "").endswith("/login")


@pytest.mark.parametrize("path", sorted(ADMIN_ONLY))
def test_admin_pages_forbidden_for_plain_member(make_client, path):
    """Een gewoon (niet-admin) lid krijgt 403 op admin-pagina's — de
    privilege-grens, niet alleen de login-grens."""
    resp = make_client("member").get(_realize(path), follow_redirects=False)
    assert resp.status_code == 403, f"{path} lid → {resp.status_code} (verwacht 403)"


# --------------------------------------------------------------------------- #
# 3. De zelf-groei-gate: elke route is geclassificeerd.                         #
# --------------------------------------------------------------------------- #
def test_route_inventory_is_acknowledged():
    """Elke live GET-route moet in precies één classificatie-bucket zitten.

    Voeg je een nieuwe pagina toe? Dan faalt deze test tot je 'm in de juiste set
    bovenin dit bestand zet — zo kan geen scherm ongeclassificeerd/ongetest
    shippen (de kern van 'ook als we verder bouwen')."""
    live = set(_all_get_routes())
    unclassified = live - ACKNOWLEDGED
    assert not unclassified, (
        "Nieuwe, niet-geclassificeerde GET-route(s) gevonden: "
        f"{sorted(unclassified)}. Zet ze in de juiste set in "
        "tests/test_uat_coverage.py (PUBLIC_INDEXABLE / MEMBER_ONLY / "
        "ADMIN_ONLY / ...), zodat de UAT ze afdwingt."
    )
    stale = ACKNOWLEDGED - live
    assert not stale, (
        f"Geclassificeerde route(s) bestaan niet meer: {sorted(stale)}. "
        "Verwijder ze uit tests/test_uat_coverage.py."
    )


def test_buckets_are_disjoint():
    """Een route mag niet in twee buckets tegelijk staan (anders is de auth-
    verwachting dubbelzinnig)."""
    buckets = {
        "PUBLIC_INDEXABLE": PUBLIC_INDEXABLE,
        "PUBLIC_NOINDEX": PUBLIC_NOINDEX,
        "PUBLIC_FRAGMENTS": PUBLIC_FRAGMENTS,
        "MEMBER_ONLY": MEMBER_ONLY,
        "ADMIN_ONLY": ADMIN_ONLY,
        "INFRA": INFRA,
        "TOKEN_ROUTES": TOKEN_ROUTES,
        "STREAMING": STREAMING,
    }
    seen: dict[str, str] = {}
    for name, routes in buckets.items():
        for r in routes:
            assert r not in seen, f"{r} staat in zowel {seen[r]} als {name}"
            seen[r] = name
