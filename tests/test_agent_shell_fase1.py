"""Agent-Shell Fase 1 — units + render-/grounding-tests.

Dekt de gesloten red-team-blockers + de kern van de pivot:
- ``tool_surface`` registry-grens + param-whitelist/type-coercion (anti-wildgroei).
- ``_wrap_surface`` single-top-level-node (htmx multi-node-blocker).
- ``concierge_state`` history-discipline (lege/whitespace nooit opgeslagen; coerce
  naar platte str; ``load_messages`` filtert lege turns — de 400-vergiftigings-fix).
- de surface-loaders + grounding-poort (verzonnen/besloten slug → None).
- ``_nav_to_surface`` (navigate→surface, incl. /leden/{slug}; /logout → None).
- de agent-canvas-shell: single-host, ``hx-ext="sse"``, één live-region (niet op
  <main>), noindex, footer-fallback met echte hrefs + <noscript>.
- ``select_chips`` (≤3, gegrond op echte tellingen, dismissed weggefilterd).

Hermetisch (geen netwerk/Postgres): SQLite + dependency-overrides, zoals de andere
route-tests.
"""

from __future__ import annotations

import pytest
from app.models import Base, Member, MemberStatus, Visibility
from app.routers import concierge as cr
from app.services import concierge_service, concierge_state, nudge_service
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# --------------------------------------------------------------------------- #
# 1. tool_surface — registry-grens + whitelist + type-coercion                #
# --------------------------------------------------------------------------- #
def test_tool_surface_unknown_view_error():
    r = concierge_service.tool_surface({"view": "verzonnen"})
    assert "error" in r
    assert "view" not in r  # error-tak draagt geen view → router rendert niets


def test_tool_surface_known_view_ok():
    r = concierge_service.tool_surface(
        {"view": "members_grid", "params": {"tag": "agents"}}
    )
    assert r == {"view": "members_grid", "params": {"tag": "agents"}}


def test_tool_surface_whitelists_param_keys():
    # 'slug' is geen toegestane key voor members_grid → gedropt; 'tag' blijft.
    r = concierge_service.tool_surface(
        {"view": "members_grid", "params": {"slug": "x", "tag": "agents"}}
    )
    assert r["params"] == {"tag": "agents"}


def test_tool_surface_drops_nonscalar_and_coerces_int():
    # list-waarde gedropt; int gecoerced naar str (anti-wildgroei + grounding-grens).
    r = concierge_service.tool_surface(
        {"view": "members_grid", "params": {"tag": ["x"], "maakt": 7}}
    )
    assert r["params"] == {"maakt": "7"}


def test_tool_draft_unknown_entity_error():
    assert "error" in concierge_service.tool_draft("verzonnen", {"title": "x"})


def test_tool_draft_whitelists_fields():
    # 'body' hoort niet bij offering → gedropt; title/description blijven.
    r = concierge_service.tool_draft(
        "offering", {"title": "T", "body": "nope", "description": "D"}
    )
    assert r == {"draft": "offering", "fields": {"title": "T", "description": "D"}}


def test_draft_tools_registered():
    names = [t["name"] for t in concierge_service.TOOLS]
    for n in ("draft_offering", "draft_need", "draft_idea"):
        assert n in names


def test_draft_partials_prefilled_and_post_to_existing_endpoints():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    cases = [
        ("concierge/_draft_offering.html", "/profiel/offering", {"title": "AI-tool"}),
        ("concierge/_draft_need.html", "/profiel/need", {"title": "Co-founder"}),
        ("concierge/_draft_idea.html", "/ideeen", {"title": "Donkere modus"}),
    ]
    for tmpl, endpoint, fields in cases:
        html = env.get_template(tmpl).render(fields=fields)
        assert f'hx-post="{endpoint}"' in html
        assert f'value="{fields["title"]}"' in html
        # Bevestigen + annuleren aanwezig; commit pas na de klik (geen auto-write).
        assert "laat maar" in html


def test_tool_draft_field_unknown_field_error():
    # tags valt bewust buiten DRAFT_FIELDS (append-semantiek) → fout.
    assert "error" in concierge_service.tool_draft_field({"field": "tags", "value": "x"})


def test_tool_draft_field_valid():
    r = concierge_service.tool_draft_field({"field": "headline", "value": "Bouwer van AI"})
    assert r == {"draft": "field", "field": "headline", "value": "Bouwer van AI"}


def test_draft_field_partial_prefilled_and_patches():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("concierge/_draft_field.html").render(
        field="headline", value="Bouwer van AI", label="Kopregel"
    )
    assert 'hx-patch="/profiel/ai/veld/headline"' in html
    assert 'value="Bouwer van AI"' in html
    assert "laat maar" in html
    # bio → textarea-variant.
    html2 = env.get_template("concierge/_draft_field.html").render(
        field="bio", value="Over mij tekst", label="Over jou"
    )
    assert "<textarea" in html2
    assert "Over mij tekst" in html2


def test_surface_registry_matches_tool_enum():
    surf = next(t for t in concierge_service.TOOLS if t["name"] == "surface")
    enum = set(surf["input_schema"]["properties"]["view"]["enum"])
    assert enum == set(concierge_service.SURFACE_REGISTRY)


# --------------------------------------------------------------------------- #
# 2. _wrap_surface — precies één top-level node                               #
# --------------------------------------------------------------------------- #
def test_wrap_surface_single_top_level_node():
    html = cr._wrap_surface("members_grid", "<div>a</div><div>b</div>")
    assert html.count("<section") == 1
    assert html.strip().startswith("<section")
    assert 'class="surface-card"' in html
    assert 'data-surface="members_grid"' in html


def test_wrap_surface_sanitises_view():
    html = cr._wrap_surface('mem"x<y', "z")
    assert 'data-surface="memxy"' in html


# --------------------------------------------------------------------------- #
# 3. _nav_to_surface — navigate→surface mapping                               #
# --------------------------------------------------------------------------- #
def test_nav_to_surface_fixed_views():
    assert cr._nav_to_surface("/leden") == ("members_grid", {})
    assert cr._nav_to_surface("/ideeen") == ("ideas_list", {})
    assert cr._nav_to_surface("/roadmap") == ("roadmap_board", {})


def test_nav_to_surface_member_slug():
    assert cr._nav_to_surface("/leden/ada-lovelace") == (
        "member_detail",
        {"slug": "ada-lovelace"},
    )


def test_nav_to_surface_logout_and_other_are_real_navigate():
    assert cr._nav_to_surface("/logout") is None
    assert cr._nav_to_surface("/profiel/ai/bouwen") is None
    assert cr._nav_to_surface("/iets-anders") is None


# --------------------------------------------------------------------------- #
# 4. concierge_state — history-discipline (de 400-vergiftigings-fix)          #
# --------------------------------------------------------------------------- #
def test_append_turn_rejects_empty_and_whitespace(db, make_member):
    m = make_member(email="state1@x.nl")
    assert concierge_state.append_turn(db, m.id, "assistant", "") is None
    assert concierge_state.append_turn(db, m.id, "user", "   ") is None
    assert concierge_state.load_messages(db, m.id) == []


def test_append_turn_coerces_nonstr_to_plain_str(db, make_member):
    m = make_member(email="state2@x.nl")
    turn = concierge_state.append_turn(db, m.id, "assistant", ["blok"])
    assert turn is not None
    assert isinstance(turn.content, str)
    msgs = concierge_state.load_messages(db, m.id)
    assert msgs and isinstance(msgs[-1]["content"], str)


def test_load_messages_filters_empty_rows_defensively(db, make_member):
    from app.models import ConciergeTurn

    m = make_member(email="state3@x.nl")
    # Schrijf direct een whitespace-rij (bypass de append_turn-poort) → de
    # load-filter is de tweede gordel.
    db.add(ConciergeTurn(member_id=m.id, role="user", content="   "))
    db.add(ConciergeTurn(member_id=m.id, role="user", content="echt"))
    db.flush()
    msgs = concierge_state.load_messages(db, m.id)
    assert [x["content"] for x in msgs] == ["echt"]


# --------------------------------------------------------------------------- #
# 5. Surface-loaders + grounding-poort                                        #
# --------------------------------------------------------------------------- #
def test_load_member_detail_real_profile(db, make_member, make_profile):
    m = make_member(email="ada@x.nl", name="Ada")
    p = make_profile(m, display_name="Ada", visibility=Visibility.public)
    loaded = cr._load_member_detail(db, {"slug": p.slug}, None, False)
    assert loaded is not None
    template, ctx = loaded
    assert template == "concierge/_card.html"
    assert ctx["profile"].slug == p.slug


def test_load_member_detail_invented_slug_is_none(db):
    assert cr._load_member_detail(db, {"slug": "bestaat-niet"}, None, False) is None


def test_load_member_detail_closed_profile_is_none(db, make_member, make_profile):
    """Grounding/AVG: een echt-maar-besloten profiel materialiseert niet."""
    m = make_member(email="dicht@x.nl", name="Besloten")
    p = make_profile(m, display_name="Besloten", visibility=Visibility.members)
    assert cr._load_member_detail(db, {"slug": p.slug}, None, False) is None


def test_load_members_grid_returns_grid_with_public(db, make_member, make_profile):
    m = make_member(email="maker@x.nl", name="Maker")
    make_profile(m, display_name="Maker", visibility=Visibility.public)
    template, ctx = cr._load_members_grid(db, {}, None, False)
    assert template == "members/_grid.html"
    assert any(getattr(p, "slug", None) for p in ctx["profiles"])


# --------------------------------------------------------------------------- #
# 6. select_chips — ≤3, gegrond op echte tellingen, dismissed weg             #
# --------------------------------------------------------------------------- #
def test_select_chips_max_three_and_roadmap_always(db, make_member, make_profile):
    m = make_member(email="chips1@x.nl")
    make_profile(m, visibility=Visibility.public)
    chips = nudge_service.select_chips(db, m)
    assert len(chips) <= 3
    assert "chip_roadmap" in [c.kind for c in chips]


def test_select_chips_grounded_no_public_no_new_members_chip(db, make_member):
    m = make_member(email="chips2@x.nl")  # geen publiek profiel
    chips = nudge_service.select_chips(db, m)
    assert "nieuwe_makers" not in [c.kind for c in chips]


def test_select_chips_dismissed_kind_filtered(db, make_member, make_profile):
    m = make_member(email="chips3@x.nl")
    make_profile(m, visibility=Visibility.public)
    nudge_service.dismiss(db, m, "chip_roadmap")
    db.flush()
    chips = nudge_service.select_chips(db, m)
    assert "chip_roadmap" not in [c.kind for c in chips]


# --------------------------------------------------------------------------- #
# 7. De agent-canvas-shell (render) + chips-route                             #
# --------------------------------------------------------------------------- #
@pytest.fixture
def route_engine():
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
    return sessionmaker(
        bind=route_engine, autoflush=False, autocommit=False, future=True
    )


@pytest.fixture
def make_client(route_engine, SessionTest):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    def _factory(member_id: int | None):
        def _override_current_member(db: Session = Depends(get_db)):
            if member_id is None:
                return None
            return db.get(Member, member_id)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def _seed_approved(SessionTest, *, public_profile=False) -> int:
    s = SessionTest()
    m = Member(email="lid@x.nl", name="Ingelogd Lid", status=MemberStatus.approved)
    s.add(m)
    s.flush()
    if public_profile:
        from app.models import Profile

        s.add(
            Profile(
                member_id=m.id,
                slug="ingelogd-lid",
                display_name="Ingelogd Lid",
                visibility=Visibility.public,
            )
        )
    s.commit()
    mid = m.id
    s.close()
    return mid


def test_canvas_single_host_and_hx_ext(make_client, SessionTest):
    """RT-FIX dubbele-host + hx-ext: exact één host-id-set, mét hx-ext='sse'."""
    mid = _seed_approved(SessionTest)
    body = make_client(mid).get("/").text
    assert body.count('id="concierge-materialisatie"') == 1
    assert body.count('id="concierge-flow"') == 1
    assert body.count('id="concierge-results"') == 1
    assert 'hx-ext="sse"' in body


def test_canvas_one_live_region_not_on_main(make_client, SessionTest):
    """RT-FIX a11y: geen aria-live op <main>; de polite-region is #concierge-flow."""
    mid = _seed_approved(SessionTest)
    body = make_client(mid).get("/").text
    assert (
        '<main role="main" aria-label="De wereld — agent-canvas" class="canvas wrap">'
        in body
    )
    assert (
        'id="concierge-flow" class="concierge-flow" role="status" aria-live="polite"'
        in body
    )


def test_canvas_noindex_and_no_main_nav(make_client, SessionTest):
    mid = _seed_approved(SessionTest)
    body = make_client(mid).get("/").text
    assert 'name="robots" content="noindex"' in body
    assert 'aria-label="Hoofdnavigatie"' not in body
    assert 'id="canvas-form"' in body


def test_canvas_footer_fallback_real_links_and_noscript(make_client, SessionTest):
    """RT-FIX footer-fallback: echte hrefs + <noscript> → werkt zonder agent/JS."""
    mid = _seed_approved(SessionTest)
    body = make_client(mid).get("/").text
    assert 'id="canvas-fallback-menu"' in body
    for href in ("/leden", "/ideeen", "/roadmap", "/profiel/ai/bouwen"):
        assert f'href="{href}"' in body
    assert 'action="/logout"' in body
    assert "<noscript>" in body


def test_canvas_firstrun_offer_for_incomplete_profile(make_client, SessionTest):
    """First-run: een lid zonder (compleet) profiel krijgt het bouw-aanbod inline."""
    mid = _seed_approved(SessionTest)  # geen profiel
    body = make_client(mid).get("/").text
    assert "canvas-firstrun" in body
    assert "Bouw mijn profiel" in body


def test_canvas_no_firstrun_for_complete_profile(make_client, SessionTest):
    from app.models import Profile

    s = SessionTest()
    m = Member(email="done@x.nl", name="Klaar", status=MemberStatus.approved)
    s.add(m)
    s.flush()
    s.add(
        Profile(
            member_id=m.id,
            slug="klaar",
            display_name="Klaar",
            visibility=Visibility.public,
            completeness=100,
        )
    )
    s.commit()
    mid = m.id
    s.close()
    body = make_client(mid).get("/").text
    assert "canvas-firstrun" not in body


def test_chips_route_renders_at_least_roadmap(make_client, SessionTest):
    mid = _seed_approved(SessionTest, public_profile=True)
    resp = make_client(mid).get("/concierge/chips")
    assert resp.status_code == 200
    assert "canvas-chip" in resp.text


def test_canvas_marks_new_makers_this_week(make_client, SessionTest):
    """Slice 2: pas-verschenen makers gloeien in de canvas-constellatie + de kop
    erkent de groei ("N nieuw deze week"). Gegrond op echte created_at, nul AI."""
    from app.models import Profile

    s = SessionTest()
    viewer = Member(email="kijker@x.nl", name="Kijker", status=MemberStatus.approved)
    s.add(viewer)
    s.flush()
    # 3 verse publieke makers (default created_at = nu → "deze week") zodat de
    # constellatie rendert (guard >= 3) én de nieuw-markering aangaat.
    for i in range(3):
        m = Member(email=f"vers{i}@x.nl", name=f"Vers {i}",
                   status=MemberStatus.approved)
        s.add(m)
        s.flush()
        s.add(Profile(member_id=m.id, slug=f"vers-{i}", display_name=f"Vers {i}",
                      visibility=Visibility.public))
    s.commit()
    mid = viewer.id
    s.close()

    body = make_client(mid).get("/").text
    assert "home-star--new" in body          # de gloed-klasse rendert
    assert "nieuw deze week" in body         # de kop erkent de groei
    assert "3 nieuw deze week" in body       # gegronde telling


def test_canvas_no_new_marker_when_makers_are_old(make_client, SessionTest):
    """Zonder recente makers blijft de constellatie rustig — geen valse gloed."""
    from datetime import timedelta

    from app.models import Profile
    from app.security import naive_utc, utcnow

    old = naive_utc(utcnow()) - timedelta(days=60)
    s = SessionTest()
    viewer = Member(email="kijker2@x.nl", name="Kijker", status=MemberStatus.approved)
    s.add(viewer)
    s.flush()
    for i in range(3):
        m = Member(email=f"oud{i}@x.nl", name=f"Oud {i}",
                   status=MemberStatus.approved)
        m.created_at = old
        s.add(m)
        s.flush()
        s.add(Profile(member_id=m.id, slug=f"oud-{i}", display_name=f"Oud {i}",
                      visibility=Visibility.public))
    s.commit()
    mid = viewer.id
    s.close()

    body = make_client(mid).get("/").text
    assert "home-constellation" in body      # de graaf rendert nog steeds
    assert "home-star--new" not in body      # maar niets gloeit als "nieuw"
    assert "nieuw deze week" not in body


def test_load_profile_builder_for_member(SessionTest):
    m = Member(email="pb@x.nl", name="Bouwer", status=MemberStatus.approved)
    s = SessionTest()
    s.add(m)
    s.commit()
    mid = m.id
    s.close()
    db2 = SessionTest()
    loaded = cr._load_profile_builder(db2, {}, mid, False)
    db2.close()
    assert loaded is not None
    template, ctx = loaded
    assert template == "concierge/_profile_builder.html"
    assert ctx["profile"].member_id == mid


def test_load_profile_builder_anon_is_none(SessionTest):
    db2 = SessionTest()
    try:
        assert cr._load_profile_builder(db2, {}, None, False) is None
    finally:
        db2.close()


def test_profielbouw_route_opens_builder_deterministically(make_client, SessionTest):
    """De first-run-CTA opent de builder via een directe route (geen LLM-gok)."""
    mid = _seed_approved(SessionTest)
    body = make_client(mid).get("/concierge/profielbouw").text
    assert "profile-builder" in body
    assert 'id="materialisatie"' in body
    assert 'hx-post="/profiel/ai/bericht"' in body


def test_demo_route_public_indexable_and_fictional(make_client):
    """De publieke demo: 200, duidelijk fictief/AI-demo, CTA naar registratie,
    indexeerbaar (geen noindex)."""
    body = make_client(None).get("/demo").text
    assert "Demo — fictief profiel" in body
    assert "Nova Belmonte" in body
    assert "studio-nova.ai" in body
    assert 'href="/register"' in body
    assert "noindex" not in body
    # Rijker: door-AI gegenereerd sfeerbeeld + tijdlijn + makers-teaser.
    assert "/static/demo-nova-cover.jpg" in body
    assert "demo-timeline" in body
    assert "Andere makers" in body
    # Startknop: de demo speelt pas ná een klik (geen instant auto-play).
    assert 'id="demo-play"' in body
    assert "Speel de demo af" in body


def test_canvas_includes_markdown_renderer(make_client, SessionTest):
    """De canvas laadt md.js zodat AI-antwoorden netjes gerenderd worden."""
    mid = _seed_approved(SessionTest)
    assert "/static/md.js" in make_client(mid).get("/").text


def test_normal_page_keeps_single_overlay_host(make_client, SessionTest):
    """Een gewone (anonieme) kosmische pagina draagt de overlay-host óók exact 1×."""
    body = make_client(None).get("/leden").text
    assert body.count('id="concierge-flow"') == 1
    assert body.count('id="concierge-materialisatie"') == 1
