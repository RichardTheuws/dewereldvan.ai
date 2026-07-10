"""Tests voor Samenkomen — de datumprikker (PRD-samenkomen, fase 1).

Kernen die we bewaken:
- create ontdubbelt/sorteert/capt datums en dropt het verleden;
- stemmen is race-veilig idempotent (uniek per datum+lid, savepoint-herstel);
- de tally telt correct + wijst de koploper(s) aan (gelijkspel = geen auto-keuze);
- resolve klapt samen tot een ECHT agenda-event (Post) met de ja-stemmers als RSVP;
- auto-selectie leunt op de interesse-graaf (gedeelde tag/tool), poort-veilig;
- de routes zijn login-gated en de htmx-stem-swap werkt.

Service-tests draaien op de rollback-geïsoleerde ``db`` (met het savepoint-recept
uit conftest); route-tests op een wegwerp-engine die echt commit (spiegelt
test_agenda_nieuws).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Gathering,
    GatheringState,
    GatheringVoteChoice,
    Post,
    PostKind,
)
from app.services import gathering_service
from tests._route_helpers import csrf_token, make_route_engine


def _future(days: int, hour: int = 19) -> datetime:
    return (datetime.now() + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


# --------------------------------------------------------------------------- #
# Service — aanmaken                                                           #
# --------------------------------------------------------------------------- #


def test_create_dedups_sorts_caps_and_drops_past(db, make_member):
    member = make_member()
    d1, d2 = _future(3), _future(10)
    past = _future(-5)
    g = gathering_service.create(
        db,
        creator=member,
        title="  Borrel  ",
        date_options=[d2, d1, d1, past],  # ongesorteerd + dubbel + verleden
    )
    assert g.title == "Borrel"
    starts = [d.starts_at for d in g.dates]
    assert starts == sorted(starts)  # gesorteerd
    assert len(starts) == 2  # dubbel weg, verleden weg


def test_create_without_future_date_raises(db, make_member):
    member = make_member()
    with pytest.raises(ValueError):
        gathering_service.create(
            db, creator=member, title="Leeg", date_options=[_future(-1)]
        )


def test_create_caps_at_max_options(db, make_member):
    member = make_member()
    many = [_future(i) for i in range(1, gathering_service.MAX_DATE_OPTIONS + 4)]
    g = gathering_service.create(db, creator=member, title="Veel", date_options=many)
    assert len(g.dates) == gathering_service.MAX_DATE_OPTIONS


# --------------------------------------------------------------------------- #
# Service — stemmen + tally                                                    #
# --------------------------------------------------------------------------- #


def test_vote_counts_and_leader(db, make_member):
    creator = make_member(email="c@example.com")
    a = make_member(email="a@example.com")
    b = make_member(email="b@example.com")
    g = gathering_service.create(
        db, creator=creator, title="X", date_options=[_future(3), _future(10)]
    )
    d1, d2 = g.dates
    gathering_service.vote(db, member=a, date=d1, choice=GatheringVoteChoice.yes)
    gathering_service.vote(db, member=b, date=d1, choice=GatheringVoteChoice.yes)
    gathering_service.vote(db, member=a, date=d2, choice=GatheringVoteChoice.maybe)

    t = gathering_service.tally(db, g)
    by_id = {dt.date.id: dt for dt in t.dates}
    assert by_id[d1.id].yes == 2
    assert by_id[d2.id].maybe == 1
    assert t.voter_count == 2
    assert t.leader_date_ids == [d1.id]  # d1 wint op ja-stemmen
    assert not t.is_tie


def test_vote_is_idempotent_and_updates_choice(db, make_member):
    creator = make_member(email="c@example.com")
    a = make_member(email="a@example.com")
    g = gathering_service.create(db, creator=creator, title="X", date_options=[_future(3)])
    d1 = g.dates[0]

    r1 = gathering_service.vote(db, member=a, date=d1, choice=GatheringVoteChoice.yes)
    assert r1.created is True
    # Zelfde lid stemt opnieuw op dezelfde datum → geen dubbele rij, keuze update.
    r2 = gathering_service.vote(db, member=a, date=d1, choice=GatheringVoteChoice.no)
    assert r2.created is False

    t = gathering_service.tally(db, g, viewer=a)
    dt = t.dates[0]
    assert dt.yes == 0 and dt.no == 1  # omgezet, niet dubbel
    assert dt.viewer_choice == "no"


def test_tie_is_flagged_not_auto_resolved(db, make_member):
    creator = make_member(email="c@example.com")
    a = make_member(email="a@example.com")
    b = make_member(email="b@example.com")
    g = gathering_service.create(
        db, creator=creator, title="X", date_options=[_future(3), _future(10)]
    )
    d1, d2 = g.dates
    gathering_service.vote(db, member=a, date=d1, choice=GatheringVoteChoice.yes)
    gathering_service.vote(db, member=b, date=d2, choice=GatheringVoteChoice.yes)
    t = gathering_service.tally(db, g)
    assert t.is_tie
    assert set(t.leader_date_ids) == {d1.id, d2.id}


# --------------------------------------------------------------------------- #
# Service — samenklappen tot event + annuleren                                 #
# --------------------------------------------------------------------------- #


def test_resolve_creates_event_with_attendance(db, make_member):
    creator = make_member(email="c@example.com")
    goer = make_member(email="g@example.com")
    g = gathering_service.create(
        db, creator=creator, title="Meetup", location_hint="Utrecht",
        date_options=[_future(3), _future(10)],
    )
    winning = g.dates[0]
    gathering_service.vote(db, member=goer, date=winning, choice=GatheringVoteChoice.yes)

    post = gathering_service.resolve(db, gathering=g, date=winning, actor=creator)
    assert post.kind == PostKind.event
    assert post.next_at == winning.starts_at
    assert post.location == "Utrecht"
    assert g.state == GatheringState.resolved
    assert g.resolved_post_id == post.id

    # De maker organiseert; de ja-stemmer gaat.
    from app.services import attendance_service

    summary = attendance_service.summary_for(db, post, viewer=goer)
    assert summary.organizing == 1
    assert summary.attending == 1


def test_resolve_is_idempotent(db, make_member):
    creator = make_member(email="c@example.com")
    g = gathering_service.create(db, creator=creator, title="X", date_options=[_future(3)])
    d1 = g.dates[0]
    p1 = gathering_service.resolve(db, gathering=g, date=d1, actor=creator)
    p2 = gathering_service.resolve(db, gathering=g, date=d1, actor=creator)
    assert p1.id == p2.id  # geen tweede event


def test_cancel_open_but_not_resolved(db, make_member):
    creator = make_member(email="c@example.com")
    g = gathering_service.create(db, creator=creator, title="X", date_options=[_future(3)])
    gathering_service.cancel(db, gathering=g)
    assert g.state == GatheringState.cancelled

    g2 = gathering_service.create(db, creator=creator, title="Y", date_options=[_future(3)])
    gathering_service.resolve(db, gathering=g2, date=g2.dates[0], actor=creator)
    gathering_service.cancel(db, gathering=g2)  # resolved → onaangeraakt
    assert g2.state == GatheringState.resolved


# --------------------------------------------------------------------------- #
# Service — auto-selectie (interesse-graaf)                                     #
# --------------------------------------------------------------------------- #


def test_suggest_interested_by_interest_tag(db, make_member, make_profile):
    from app.models import Tag

    creator = make_member(email="c@example.com")
    make_profile(creator)
    match = make_member(email="m@example.com")
    mp = make_profile(match, display_name="Voice Maker")
    voter = make_member(email="v@example.com")
    vp = make_profile(voter, display_name="Al Gestemd")

    tag = Tag(name="voice-agents", slug="voice-agents")
    db.add(tag)
    db.flush()
    mp.tags.append(tag)
    vp.tags.append(tag)
    db.flush()

    g = gathering_service.create(
        db, creator=creator, title="Borrel", interest="voice-agents",
        date_options=[_future(3)],
    )
    # 'voter' heeft al gestemd → moet uit de suggestie vallen.
    gathering_service.vote(db, member=voter, date=g.dates[0], choice=GatheringVoteChoice.yes)

    suggested = gathering_service.suggest_interested(db, g)
    slugs = {s.profile.slug for s in suggested}
    assert mp.slug in slugs  # gematcht op tag
    assert vp.slug not in slugs  # al gestemd → uitgesloten
    assert creator.id not in {s.profile.member_id for s in suggested}  # niet jezelf


# --------------------------------------------------------------------------- #
# Routes — auth-poort + de volledige flow                                      #
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
    from app.models import Member, MemberStatus

    s = SessionTest()
    creator = Member(email="c@example.com", name="Starter", status=MemberStatus.approved)
    other = Member(email="o@example.com", name="Ander Lid", status=MemberStatus.approved)
    s.add_all([creator, other])
    s.commit()
    ids = {"creator": creator.id, "other": other.id}
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
            return db.get(Member, member_id) if member_id is not None else None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[current_member] = _override_current_member
        return TestClient(app, base_url="https://testserver")

    yield _factory
    app.dependency_overrides.clear()


def test_index_requires_login(make_client):
    client = make_client(None)
    resp = client.get("/samen", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].endswith("/login")


def test_create_vote_and_resolve_flow(make_client, SessionTest, seed):
    client = make_client(seed["creator"])
    token = csrf_token(client, "/samen/nieuw")
    resp = client.post(
        "/samen",
        data={
            "title": "Makersborrel",
            "location_hint": "Utrecht",
            "datum": [_future(3).isoformat(timespec="minutes"),
                      _future(10).isoformat(timespec="minutes")],
        },
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc.startswith("/samen/")
    gid = int(loc.rsplit("/", 1)[1])

    # De detailpagina toont de constellatie.
    detail = client.get(loc)
    assert detail.status_code == 200
    assert "Makersborrel" in detail.text

    # Haal een datum-id op en stem 'ja' (htmx-swap geeft de verse constellatie).
    s = SessionTest()
    g = s.get(Gathering, gid)
    date_id = g.dates[0].id
    s.close()

    vote = client.post(
        f"/samen/{gid}/stem",
        data={"date_id": date_id, "choice": "yes"},
        headers={"X-CSRF-Token": token},
    )
    assert vote.status_code == 200
    assert "1 kan" in vote.text  # de telling staat in het fragment

    # De maker kiest de winnende datum → doorverwijzing naar de agenda.
    chosen = client.post(
        f"/samen/{gid}/kies",
        data={"date_id": date_id},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    assert chosen.status_code == 303
    assert chosen.headers["location"].endswith("/agenda")

    # Er staat nu een echt agenda-event.
    s = SessionTest()
    events = s.query(Post).filter(Post.kind == PostKind.event).all()
    assert any(e.title == "Makersborrel" for e in events)
    s.close()


def test_non_creator_cannot_resolve(make_client, SessionTest, seed):
    # Maker maakt de prikker.
    creator = make_client(seed["creator"])
    token = csrf_token(creator, "/samen/nieuw")
    resp = creator.post(
        "/samen",
        data={"title": "X", "datum": [_future(3).isoformat(timespec="minutes")]},
        headers={"X-CSRF-Token": token},
        follow_redirects=False,
    )
    gid = int(resp.headers["location"].rsplit("/", 1)[1])
    s = SessionTest()
    date_id = s.get(Gathering, gid).dates[0].id
    s.close()

    # Een ander lid probeert te kiezen → 403.
    other = make_client(seed["other"])
    token2 = csrf_token(other, "/samen/nieuw")
    forbidden = other.post(
        f"/samen/{gid}/kies",
        data={"date_id": date_id},
        headers={"X-CSRF-Token": token2},
        follow_redirects=False,
    )
    assert forbidden.status_code == 403
