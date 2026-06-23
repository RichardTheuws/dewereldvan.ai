"""Tests voor agenda + nieuws (Post): plaatsen, validatie, rate-limit, sortering,
admin-moderatie, en de AVG-nullify bij accountverwijdering.

Eén holistische ``Post``-entiteit met ``kind`` ∈ {event, nieuws}. Kernen die we
bewaken:
- elk goedgekeurd lid plaatst direct zichtbaar (geen wachtrij);
- events sorteren aankomend-eerst, nieuws nieuwste-eerst;
- ``added_by_id`` is SET NULL → een gewist account laat de bijdrage staan.

Geen netwerk: ``current_member`` wordt overschreven; een wegwerp-engine per test
houdt rijen hermetisch (spiegelt test_ideas).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests._route_helpers import csrf_token, make_route_engine


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture
def route_engine():
    eng = make_route_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(
        bind=route_engine, autoflush=False, autocommit=False, future=True
    )


@pytest.fixture
def seed(SessionTest):
    from app.models import Member, MemberRole, MemberStatus

    s = SessionTest()
    member = Member(email="a@example.com", name="Lid A", status=MemberStatus.approved)
    admin = Member(
        email="admin@example.com",
        name="Beheerder",
        status=MemberStatus.approved,
        role=MemberRole.admin,
    )
    pending = Member(email="p@example.com", name="Wacht", status=MemberStatus.pending)
    s.add_all([member, admin, pending])
    s.commit()
    ids = {"member": member.id, "admin": admin.id, "pending": pending.id}
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


# --------------------------------------------------------------------------- #
# Auth-poort                                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", ["/agenda", "/nieuws"])
def test_anonymous_can_read_pages(make_client, path):
    """Anon mag agenda + nieuws gewoon lezen (open platform) — geen login-redirect,
    indexeerbaar (geen noindex), met de open-preview-banner. Toevoegen blijft gated."""
    client = make_client(None)
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 200
    assert "Word lid" in resp.text  # anon ziet de uitnodiging i.p.v. het formulier
    assert 'name="title"' not in resp.text  # het toevoeg-formulier is verborgen
    assert 'name="robots" content="noindex' not in resp.text  # publiek indexeerbaar


@pytest.mark.parametrize("path", ["/agenda", "/nieuws"])
def test_anonymous_cannot_post(make_client, path):
    """De schrijfkant blijft login-gated: anon POST (mét geldige CSRF) → login."""
    client = make_client(None)
    token = csrf_token(client, path)  # anon kan nu de pagina laden → geldige token
    resp = client.post(
        path, data={"title": "x"}, headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


@pytest.mark.parametrize("path", ["/agenda", "/nieuws"])
def test_approved_member_sees_smart_input(make_client, seed, path):
    """Ingelogd lid ziet de slimme één-input (geen kale form als startpunt)."""
    client = make_client(seed["member"])
    resp = client.get(path)
    assert resp.status_code == 200
    assert "Laat de agent het invullen" in resp.text  # de smart-input
    assert 'name="input"' in resp.text


@pytest.mark.parametrize("path,name", [("/agenda/concept", "title"), ("/nieuws/concept", "title")])
def test_concept_returns_prefilled_form(make_client, seed, path, name):
    """De concept-route maakt (AI uit → fail-safe) een pre-filled concept-form: de
    titel uit de vrije tekst staat erin, klaar om te controleren en te plaatsen."""
    client = make_client(seed["member"])
    base = path.rsplit("/", 1)[0]
    token = csrf_token(client, base)
    resp = client.post(path, data={"input": "AImelo meetup in Almelo"},
                        headers={"X-CSRF-Token": token})
    assert resp.status_code == 200
    assert "Concept" in resp.text  # de controleer-&-plaats-kop
    assert "AImelo meetup in Almelo" in resp.text  # titel uit de vrije input
    assert f'name="{name}"' in resp.text


@pytest.mark.parametrize("path", ["/agenda/concept", "/nieuws/concept"])
def test_concept_requires_login(make_client, path):
    client = make_client(None)
    base = path.rsplit("/", 1)[0]
    token = csrf_token(client, base)
    resp = client.post(path, data={"input": "x"}, headers={"X-CSRF-Token": token},
                       follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")


# --------------------------------------------------------------------------- #
# Agenda — plaatsen + validatie                                               #
# --------------------------------------------------------------------------- #
def test_submit_event_persists(make_client, seed, SessionTest):
    from app.models import EventCategory, EventFrequency, Post, PostKind

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        "/agenda",
        data={
            "title": "Aimelo meetup",
            "frequency": "wekelijks",
            "category": "coding",
            "location": "Almelo",
            "cadence_note": "elke woensdag",
            "url": "https://aimelo.nl",
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "Aimelo meetup" in resp.text

    s = SessionTest()
    try:
        rows = s.query(Post).all()
        assert len(rows) == 1
        assert rows[0].kind == PostKind.event
        assert rows[0].frequency == EventFrequency.wekelijks
        assert rows[0].category == EventCategory.coding
        assert rows[0].added_by_id == seed["member"]
    finally:
        s.close()


def test_submit_event_defaults_to_meetup_category(make_client, seed, SessionTest):
    """Geen categorie meegestuurd → veilige default ``meetup`` (de form-default)."""
    from app.models import EventCategory, Post

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        "/agenda",
        data={"title": "Zonder soort", "frequency": "eenmalig"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    s = SessionTest()
    try:
        assert s.query(Post).one().category == EventCategory.meetup
    finally:
        s.close()


def test_list_events_filters_by_category(SessionTest, seed):
    """Service-filter: alleen events van de gevraagde categorie; een onbekende/
    lege waarde negeert de filter (alle events)."""
    from app.models import EventCategory, EventFrequency, Post, PostKind
    from app.services import post_service

    s = SessionTest()
    s.add_all([
        Post(kind=PostKind.event, title="Code-avond", frequency=EventFrequency.wekelijks,
             category=EventCategory.coding, added_by_id=seed["member"]),
        Post(kind=PostKind.event, title="Grote conf", frequency=EventFrequency.eenmalig,
             category=EventCategory.conferentie, added_by_id=seed["member"]),
        Post(kind=PostKind.event, title="Oud event zonder soort",
             frequency=EventFrequency.eenmalig, category=None, added_by_id=seed["member"]),
    ])
    s.commit()
    try:
        coding = post_service.list_events(s, category="coding")
        assert [p.title for p in coding] == ["Code-avond"]
        # Onbekende waarde → genegeerd (alle drie events).
        assert len(post_service.list_events(s, category="zomaar")) == 3
        # Lege/geen waarde → alle events.
        assert len(post_service.list_events(s)) == 3
    finally:
        s.close()


def test_agenda_filter_chip_end_to_end(make_client, seed, SessionTest):
    """GET /agenda?category=… (htmx-fragment) toont alleen de matchende events."""
    from app.models import EventCategory, EventFrequency, Post, PostKind

    s = SessionTest()
    s.add_all([
        Post(kind=PostKind.event, title="Workshop prompting", frequency=EventFrequency.eenmalig,
             category=EventCategory.workshop, added_by_id=seed["member"]),
        Post(kind=PostKind.event, title="Meetup Almelo", frequency=EventFrequency.wekelijks,
             category=EventCategory.meetup, added_by_id=seed["member"]),
    ])
    s.commit()
    s.close()

    client = make_client(seed["member"])
    resp = client.get("/agenda?category=workshop", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "Workshop prompting" in resp.text
    assert "Meetup Almelo" not in resp.text


def test_agenda_has_contextual_concierge_placeholder(make_client, seed):
    """Bug-fix: concierge_context='agenda' had geen branch → generieke placeholder.
    De agenda toont nu z'n eigen, contextuele prompt (geen doorval meer)."""
    page = make_client(seed["member"]).get("/agenda")
    assert page.status_code == 200
    assert "welke events passen bij mij?" in page.text
    # Niet langer de generieke fallback voor dit scherm.
    assert "Vraag de wereld iets…" not in page.text


def test_agenda_renders_countdown_filter_end_to_end(make_client, seed, SessionTest):
    """Een event mét next_at moet door de echte template-env (relatieve_tijd-filter)
    renderen zonder fout — de countdown verschijnt op de pagina."""
    from app.models import EventFrequency, Post, PostKind
    from app.security import utcnow

    s = SessionTest()
    s.add(Post(kind=PostKind.event, title="Binnenkort", frequency=EventFrequency.wekelijks,
               next_at=utcnow() + timedelta(days=3), added_by_id=seed["member"]))
    s.commit()
    s.close()

    client = make_client(seed["member"])
    page = client.get("/agenda")
    assert page.status_code == 200
    assert "Binnenkort" in page.text
    assert "over 3 dagen" in page.text  # de countdown-filter draaide


def test_submit_event_without_title_is_rejected(make_client, seed, SessionTest):
    from app.models import Post

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        "/agenda",
        data={"title": "", "frequency": "wekelijks"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400
    s = SessionTest()
    try:
        assert s.query(Post).count() == 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Nieuws — plaatsen + validatie (link verplicht)                              #
# --------------------------------------------------------------------------- #
def test_submit_news_persists(make_client, seed, SessionTest):
    from app.models import NewsRole, Post, PostKind

    client = make_client(seed["member"])
    token = csrf_token(client, "/nieuws")
    resp = client.post(
        "/nieuws",
        data={
            "title": "Interview met een bouwer",
            "url": "https://example.com/artikel",
            "role": "geinterviewd",
            "source": "Emerce",
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert "Interview met een bouwer" in resp.text

    s = SessionTest()
    try:
        rows = s.query(Post).all()
        assert len(rows) == 1
        assert rows[0].kind == PostKind.nieuws
        assert rows[0].role == NewsRole.geinterviewd
    finally:
        s.close()


def test_submit_news_without_url_is_rejected(make_client, seed, SessionTest):
    from app.models import Post

    client = make_client(seed["member"])
    token = csrf_token(client, "/nieuws")
    resp = client.post(
        "/nieuws",
        data={"title": "Zonder link", "url": ""},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400
    s = SessionTest()
    try:
        assert s.query(Post).count() == 0
    finally:
        s.close()


def test_submit_news_with_bad_url_is_rejected(make_client, seed):
    client = make_client(seed["member"])
    token = csrf_token(client, "/nieuws")
    resp = client.post(
        "/nieuws",
        data={"title": "Rare link", "url": "javascript:alert(1)"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Rate-limit (gedeeld over events + nieuws)                                    #
# --------------------------------------------------------------------------- #
def test_rate_limit_blocks_after_budget(make_client, seed, SessionTest, monkeypatch):
    from app.config import settings
    from app.models import Post

    monkeypatch.setattr(settings, "rate_limit_post_per_hour", 2)
    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    for i in range(2):
        r = client.post(
            "/agenda",
            data={"title": f"Event {i}", "frequency": "eenmalig"},
            headers={"X-CSRF-Token": token},
        )
        assert r.status_code == 200
    # derde overschrijdt het budget
    r = client.post(
        "/nieuws",
        data={"title": "Te veel", "url": "https://example.com"},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 429
    s = SessionTest()
    try:
        assert s.query(Post).count() == 2  # de geblokkeerde is niet geschreven
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Admin-moderatie — verbergen filtert uit de lijst                            #
# --------------------------------------------------------------------------- #
def test_admin_hide_removes_from_list(make_client, seed, SessionTest):
    from app.models import Post, PostKind

    s = SessionTest()
    post = Post(added_by_id=seed["member"], kind=PostKind.nieuws, title="Verbergmij",
                url="https://example.com")
    s.add(post)
    s.commit()
    post_id = post.id
    s.close()

    admin = make_client(seed["admin"])
    token = csrf_token(admin, "/nieuws")
    resp = admin.post(
        f"/admin/posts/{post_id}/verberg", headers={"X-CSRF-Token": token}
    )
    assert resp.status_code == 200

    # lid ziet 'm niet meer
    member = make_client(seed["member"])
    page = member.get("/nieuws")
    assert "Verbergmij" not in page.text


def test_non_admin_cannot_hide(make_client, seed, SessionTest):
    from app.models import Post, PostKind

    s = SessionTest()
    post = Post(added_by_id=seed["member"], kind=PostKind.event, title="X")
    s.add(post)
    s.commit()
    post_id = post.id
    s.close()

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        f"/admin/posts/{post_id}/verberg",
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303, 403)


# --------------------------------------------------------------------------- #
# Service-laag — sortering                                                     #
# --------------------------------------------------------------------------- #
def test_list_events_upcoming_first(SessionTest, seed):
    from app.models import EventFrequency, Post, PostKind
    from app.security import utcnow
    from app.services import post_service

    now = utcnow()
    s = SessionTest()
    soon = Post(kind=PostKind.event, title="Binnenkort", frequency=EventFrequency.eenmalig,
                next_at=now + timedelta(days=2))
    later = Post(kind=PostKind.event, title="Later", frequency=EventFrequency.eenmalig,
                 next_at=now + timedelta(days=20))
    past = Post(kind=PostKind.event, title="Verleden", frequency=EventFrequency.eenmalig,
                next_at=now - timedelta(days=5))
    undated = Post(kind=PostKind.event, title="Doorlopend",
                   frequency=EventFrequency.doorlopend, next_at=None)
    s.add_all([past, later, undated, soon])
    s.commit()
    events = post_service.list_events(s)
    titles = [e.title for e in events]
    # aankomend (soon < later) eerst, dan zonder-datum, dan verleden achteraan
    assert titles.index("Binnenkort") < titles.index("Later")
    assert titles.index("Later") < titles.index("Verleden")
    assert titles.index("Doorlopend") < titles.index("Verleden")
    s.close()


def test_list_news_newest_first(SessionTest):
    from app.models import NewsRole, Post, PostKind
    from app.security import utcnow
    from app.services import post_service

    now = utcnow()
    s = SessionTest()
    oud = Post(kind=PostKind.nieuws, title="Oud", url="https://a", role=NewsRole.gedeeld,
               published_at=now - timedelta(days=30))
    nieuw = Post(kind=PostKind.nieuws, title="Nieuw", url="https://b", role=NewsRole.gedeeld,
                 published_at=now - timedelta(days=1))
    s.add_all([oud, nieuw])
    s.commit()
    items = post_service.list_news(s)
    assert [i.title for i in items] == ["Nieuw", "Oud"]
    s.close()


def test_hidden_excluded_from_lists(SessionTest):
    from app.models import NewsRole, Post, PostKind
    from app.services import post_service

    s = SessionTest()
    visible = Post(kind=PostKind.nieuws, title="Zichtbaar", url="https://a",
                   role=NewsRole.gedeeld)
    hidden = Post(kind=PostKind.nieuws, title="Verborgen", url="https://b",
                  role=NewsRole.gedeeld, hidden=True)
    s.add_all([visible, hidden])
    s.commit()
    titles = [i.title for i in post_service.list_news(s)]
    assert titles == ["Zichtbaar"]
    s.close()


# --------------------------------------------------------------------------- #
# AVG — accountverwijdering laat de bijdrage staan (added_by → NULL)          #
# --------------------------------------------------------------------------- #
def test_account_deletion_nullifies_post_author(SessionTest, seed):
    from app.models import Member, Post, PostKind
    from app.services.account_deletion import delete_member_completely

    s = SessionTest()
    post = Post(added_by_id=seed["member"], kind=PostKind.event, title="Blijft staan")
    s.add(post)
    s.commit()
    post_id = post.id

    member = s.get(Member, seed["member"])
    delete_member_completely(s, member)
    s.commit()

    survivor = s.get(Post, post_id)
    assert survivor is not None  # community-waarde blijft
    assert survivor.added_by_id is None  # geen anker meer naar het gewiste lid
    s.close()


# --------------------------------------------------------------------------- #
# RSVP / aanwezigheid (de sociale laag)                                       #
# --------------------------------------------------------------------------- #
def _event(s, seed, title="Meetup"):
    from app.models import EventFrequency, Post, PostKind

    post = Post(added_by_id=seed["member"], kind=PostKind.event, title=title,
                frequency=EventFrequency.eenmalig)
    s.add(post)
    s.commit()
    return post


def test_rsvp_set_role_upserts(SessionTest, seed):
    """Eén rol per lid per event: een rol wijzigen update de rij i.p.v. te dupliceren."""
    from app.models import EventAttendance, EventAttendanceRole, Member
    from app.services import attendance_service

    s = SessionTest()
    post = _event(s, seed)
    member = s.get(Member, seed["member"])
    attendance_service.set_role(s, member=member, post=post, role=EventAttendanceRole.attending)
    s.commit()
    attendance_service.set_role(s, member=member, post=post, role=EventAttendanceRole.speaking)
    s.commit()
    rows = s.query(EventAttendance).all()
    assert len(rows) == 1  # geen dubbele rij
    assert rows[0].role == EventAttendanceRole.speaking
    s.close()


def test_rsvp_summary_counts_and_names(SessionTest, seed):
    """De summary telt per rol + benoemt sprekers/organisatoren + de eigen keuze."""
    from app.models import EventAttendanceRole, Member
    from app.services import attendance_service

    s = SessionTest()
    post = _event(s, seed)
    a = s.get(Member, seed["member"])   # "Lid A"
    b = s.get(Member, seed["admin"])    # "Beheerder"
    attendance_service.set_role(s, member=a, post=post, role=EventAttendanceRole.speaking)
    attendance_service.set_role(s, member=b, post=post, role=EventAttendanceRole.attending)
    s.commit()
    summary = attendance_service.summary_for(s, post, viewer=a)
    assert summary.total == 2
    assert summary.speaking == 1 and summary.attending == 1
    assert summary.viewer_role == "speaking"
    assert [att.name for att in summary.speakers] == ["Lid A"]
    assert summary.speakers[0].slug is None  # geen publiek profiel → geen link
    s.close()


def test_rsvp_route_swaps_strip(make_client, seed, SessionTest):
    """Lid meldt zich aan → strip komt terug met de telling + de eigen keuze actief."""
    from app.models import EventAttendance

    s = SessionTest()
    post = _event(s, seed)
    pid = post.id
    s.close()

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        f"/agenda/{pid}/rsvp", data={"role": "attending"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200
    assert f'id="rsvp-{pid}"' in resp.text
    assert "1 gaat" in resp.text
    assert 'aria-pressed="true"' in resp.text  # eigen keuze actief gemarkeerd

    s = SessionTest()
    assert s.query(EventAttendance).count() == 1
    s.close()


def test_rsvp_clear_removes_attendance(make_client, seed, SessionTest):
    from app.models import EventAttendance, EventAttendanceRole, Member
    from app.services import attendance_service

    s = SessionTest()
    post = _event(s, seed)
    pid = post.id
    member = s.get(Member, seed["member"])
    attendance_service.set_role(s, member=member, post=post, role=EventAttendanceRole.attending)
    s.commit()
    s.close()

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(f"/agenda/{pid}/rsvp/clear", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200
    s = SessionTest()
    assert s.query(EventAttendance).count() == 0
    s.close()


def test_anon_cannot_rsvp(make_client, seed, SessionTest):
    """RSVP is login-gated; anon POST → /login en er ontstaat geen aanmelding."""
    from app.models import EventAttendance

    s = SessionTest()
    pid = _event(s, seed).id
    s.close()

    client = make_client(None)
    token = csrf_token(client, "/agenda")
    resp = client.post(
        f"/agenda/{pid}/rsvp", data={"role": "attending"},
        headers={"X-CSRF-Token": token}, follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert resp.headers["location"].endswith("/login")
    s = SessionTest()
    assert s.query(EventAttendance).count() == 0
    s.close()


def test_rsvp_invalid_role_rejected(make_client, seed, SessionTest):
    from app.models import EventAttendance

    s = SessionTest()
    pid = _event(s, seed).id
    s.close()

    client = make_client(seed["member"])
    token = csrf_token(client, "/agenda")
    resp = client.post(
        f"/agenda/{pid}/rsvp", data={"role": "zomaar"},
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 400
    s = SessionTest()
    assert s.query(EventAttendance).count() == 0
    s.close()


def test_account_deletion_wipes_attendance(SessionTest, seed):
    """AVG: een gewist lid verliest z'n aanmeldingen; het event zelf blijft."""
    from app.models import EventAttendance, EventAttendanceRole, Member, Post
    from app.services import attendance_service
    from app.services.account_deletion import delete_member_completely

    s = SessionTest()
    post = _event(s, seed)
    post_id = post.id
    member = s.get(Member, seed["member"])
    attendance_service.set_role(s, member=member, post=post, role=EventAttendanceRole.attending)
    s.commit()

    delete_member_completely(s, member)
    s.commit()
    assert s.query(EventAttendance).count() == 0  # eigen aanmelding weg
    assert s.get(Post, post_id) is not None  # event blijft (community-waarde)
    s.close()


# --------------------------------------------------------------------------- #
# Admin — agenda-shortlist (AI-gecureerde event-kandidaten, Increment 3)       #
# --------------------------------------------------------------------------- #
def _pending_event(s, title="Twijfel-event"):
    from app.services import post_service

    return post_service.create_curated_event(
        s, title=title, url=f"https://example.com/{title}", confidence=70, live=False,
    )


def test_admin_event_shortlist_lists_pending(make_client, seed, SessionTest):
    """De shortlist toont pending event-kandidaten; live events horen er niet bij."""
    from app.services import post_service

    s = SessionTest()
    _pending_event(s, "Wacht-op-keur")
    post_service.create_curated_event(
        s, title="Al-live", url="https://example.com/live", confidence=95, live=True,
    )
    s.commit()
    s.close()

    client = make_client(seed["admin"])
    resp = client.get("/admin/agenda")
    assert resp.status_code == 200
    assert "Wacht-op-keur" in resp.text
    assert "Al-live" not in resp.text


def test_admin_event_approve_makes_live(make_client, seed, SessionTest):
    from app.models import Post, PostReviewState

    s = SessionTest()
    post = _pending_event(s)
    s.commit()
    pid = post.id
    s.close()

    client = make_client(seed["admin"])
    token = csrf_token(client, "/admin/agenda")
    resp = client.post(f"/admin/agenda/{pid}/keur-goed", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200
    s = SessionTest()
    assert s.get(Post, pid).review_state == PostReviewState.live
    s.close()


def test_admin_event_reject(make_client, seed, SessionTest):
    from app.models import Post, PostReviewState

    s = SessionTest()
    post = _pending_event(s)
    s.commit()
    pid = post.id
    s.close()

    client = make_client(seed["admin"])
    token = csrf_token(client, "/admin/agenda")
    resp = client.post(f"/admin/agenda/{pid}/weiger", headers={"X-CSRF-Token": token})
    assert resp.status_code == 200
    s = SessionTest()
    assert s.get(Post, pid).review_state == PostReviewState.rejected
    s.close()


def test_non_admin_cannot_see_event_shortlist(make_client, seed):
    """De agenda-shortlist is admin-only."""
    client = make_client(seed["member"])
    resp = client.get("/admin/agenda", follow_redirects=False)
    assert resp.status_code in (302, 303, 403)


def test_curated_live_event_appears_on_public_agenda(SessionTest, seed):
    """Een auto-goedgekeurd (live) AI-event staat publiek op de agenda; een pending
    kandidaat niet (de live-poort in _visible)."""
    from app.security import utcnow
    from app.services import post_service

    s = SessionTest()
    post_service.create_curated_event(
        s, title="Auto-live event", url="https://example.com/auto", confidence=95,
        live=True, next_at=utcnow() + timedelta(days=5), location="Online",
    )
    post_service.create_curated_event(
        s, title="Pending event", url="https://example.com/pend", confidence=70, live=False,
    )
    s.commit()
    titles = [e.title for e in post_service.list_events(s)]
    assert "Auto-live event" in titles
    assert "Pending event" not in titles
    s.close()


# --------------------------------------------------------------------------- #
# Helpers — relatieve_tijd / nl_datum                                         #
# --------------------------------------------------------------------------- #
def test_relatieve_tijd_buckets():
    from app.security import utcnow
    from app.services.post_service import relatieve_tijd

    now = utcnow()
    assert relatieve_tijd(now, now=now) == "vandaag"
    assert relatieve_tijd(now + timedelta(days=1), now=now) == "morgen"
    assert relatieve_tijd(now + timedelta(days=3), now=now) == "over 3 dagen"
    assert relatieve_tijd(now - timedelta(days=2), now=now) == "geweest"
    assert relatieve_tijd(None) == ""


def test_nl_datum_format():
    from datetime import datetime

    from app.services.post_service import nl_datum

    assert nl_datum(datetime(2026, 6, 24, 18, 0)) == "24 jun 2026"
    assert nl_datum(None) == ""


# --------------------------------------------------------------------------- #
# Fase 2 — agent-integratie (surfaces + draft-tools)                          #
# --------------------------------------------------------------------------- #
def test_agenda_nieuws_in_surface_registry_and_enum():
    from app.services import concierge_service

    assert "agenda" in concierge_service.SURFACE_REGISTRY
    assert "nieuws" in concierge_service.SURFACE_REGISTRY
    surf = next(t for t in concierge_service.TOOLS if t["name"] == "surface")
    enum = set(surf["input_schema"]["properties"]["view"]["enum"])
    assert enum == set(concierge_service.SURFACE_REGISTRY)  # geen drift


def test_draft_event_news_tools_registered_and_dispatch():
    from app.services import concierge_service

    names = [t["name"] for t in concierge_service.TOOLS]
    assert "draft_event" in names
    assert "draft_news" in names

    # whitelist + signaalvorm (verzonnen veld 'rommel' wordt gedropt)
    ev = concierge_service.tool_draft(
        "event", {"title": "Meetup", "frequency": "wekelijks", "rommel": "x"}
    )
    assert ev == {"draft": "event", "fields": {"title": "Meetup", "frequency": "wekelijks"}}

    # dispatch via run_tool (entity-mapping draft_news → 'nieuws')
    res, slugs = concierge_service.run_tool(
        None, "draft_news", {"title": "Artikel", "url": "https://x"}, viewer=None
    )
    assert res == {"draft": "nieuws", "fields": {"title": "Artikel", "url": "https://x"}}
    assert slugs == []


def test_draft_partials_post_to_real_endpoints():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader("app/templates"),
        autoescape=select_autoescape(["html"]),
    )
    html_ev = env.get_template("concierge/_draft_event.html").render(
        fields={"title": "Aimelo meetup", "frequency": "wekelijks"}
    )
    assert 'hx-post="/agenda"' in html_ev
    assert 'value="Aimelo meetup"' in html_ev
    assert "laat maar" in html_ev

    html_nw = env.get_template("concierge/_draft_news.html").render(
        fields={"title": "Interview", "url": "https://example.com", "role": "geinterviewd"}
    )
    assert 'hx-post="/nieuws"' in html_nw
    assert 'value="https://example.com"' in html_nw
    assert "laat maar" in html_nw


def test_nav_to_surface_agenda_nieuws():
    from app.routers import concierge as cr

    assert cr._nav_to_surface("/agenda") == ("agenda", {})
    assert cr._nav_to_surface("/nieuws") == ("nieuws", {})


def test_surface_loaders_return_lists(SessionTest, seed):
    from app.models import NewsRole, Post, PostKind
    from app.routers import concierge as cr

    s = SessionTest()
    s.add_all([
        Post(kind=PostKind.event, title="E1", added_by_id=seed["member"]),
        Post(kind=PostKind.nieuws, title="N1", url="https://a", role=NewsRole.gedeeld),
    ])
    s.commit()

    tmpl_a, ctx_a = cr._load_agenda(s, {}, seed["member"], False)
    assert tmpl_a == "agenda/_list.html"
    assert any(e.title == "E1" for e in ctx_a["events"])

    tmpl_n, ctx_n = cr._load_nieuws(s, {}, seed["member"], False)
    assert tmpl_n == "nieuws/_list.html"
    assert any(i.title == "N1" for i in ctx_n["items"])
    s.close()
