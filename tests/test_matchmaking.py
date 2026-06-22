"""Tests voor matchmaking (Tier 1): kandidaat-generatie, de gated LLM-judge,
persist/idempotentie, perspectief-weergave, de push-chip, de surface-loader en
de AVG-cascade.

De Claude-call (`_judge`) wordt gemonkeypatcht of via ``ai_enrich_enabled=False``
uitgezet — geen netwerk in de suite. Een wegwerp-engine per test houdt rijen
hermetisch (spiegelt test_agenda_nieuws).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from tests._route_helpers import make_route_engine


@pytest.fixture
def route_engine():
    eng = make_route_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(bind=route_engine, autoflush=False, autocommit=False, future=True)


def _member(s, email, name):
    from app.models import Member, MemberStatus

    m = Member(email=email, name=name, status=MemberStatus.approved)
    s.add(m)
    s.flush()
    return m


def _profile(s, member, slug):
    from app.models import Profile, Visibility

    p = Profile(
        member_id=member.id, slug=slug, display_name=member.name,
        visibility=Visibility.members, completeness=50,
    )
    s.add(p)
    s.flush()
    return p


def _offering(s, profile, title, description=""):
    from app.models import Offering

    o = Offering(profile_id=profile.id, title=title, description=description)
    s.add(o)
    s.flush()
    return o


def _need(s, profile, title, description=""):
    from app.models import Need

    n = Need(profile_id=profile.id, title=title, description=description)
    s.add(n)
    s.flush()
    return n


@pytest.fixture
def seed(SessionTest):
    """Zoeker A (need: 'voice agents'), maker B (offering: 'voice agent platform'),
    plus een niet-passende maker C (offering: 'boekhouding')."""
    s = SessionTest()
    a = _member(s, "a@x.nl", "Alice")
    b = _member(s, "b@x.nl", "Bob")
    c = _member(s, "c@x.nl", "Carol")
    pa = _profile(s, a, "alice")
    pb = _profile(s, b, "bob")
    pc = _profile(s, c, "carol")
    need = _need(s, pa, "Hulp met voice agents", "Ik zoek iemand voor spraak-evaluatie van voice agents.")
    off_b = _offering(s, pb, "Voice agent platform", "Wij bouwen voice agents en spraak-evaluatie.")
    _offering(s, pc, "Boekhoudsoftware", "Administratie voor ondernemers.")
    s.commit()
    ids = {"a": a.id, "b": b.id, "c": c.id, "need": need.id, "off_b": off_b.id}
    s.close()
    return ids


# --------------------------------------------------------------------------- #
# Kandidaat-generatie                                                         #
# --------------------------------------------------------------------------- #
def test_candidates_rank_by_overlap_and_exclude_self(SessionTest, seed):
    from app.models import Need, Profile
    from app.services import match_service

    s = SessionTest()
    need = s.get(Need, seed["need"])
    seeker = need.profile
    others = match_service._approved_profiles(s)
    cands = match_service.candidate_offerings_for_need(need, seeker, others)
    titles = [o.title for o, _ in cands]
    # 'Voice agent platform' deelt woorden ('voice','agent','spraak','evaluatie');
    # 'Boekhoudsoftware' niet → valt buiten de kandidaten.
    assert "Voice agent platform" in titles
    assert "Boekhoudsoftware" not in titles
    # eigen offerings doen niet mee
    assert all(p.id != seeker.id for _, p in cands)
    s.close()


def test_candidates_boost_offering_by_desired_discipline(SessionTest):
    """Discovery-op-discipline: een vraag om een 'workshop' haalt een workshop-
    werk-item naar voren, óók als de woorden nauwelijks overlappen."""
    from app.models import Need, OfferingKind, Profile
    from app.services import match_service

    s = SessionTest()
    a = _member(s, "seek@x.nl", "Seeker")
    b = _member(s, "train@x.nl", "Trainer")
    pa = _profile(s, a, "seeker")
    pb = _profile(s, b, "trainer")
    need = _need(s, pa, "Ik zoek een workshop over agenten", "")
    ws = _offering(s, pb, "Sessie: bouw je eigen assistent", "Een hands-on dag.")
    ws.kind = OfferingKind.workshop
    s.commit()

    seeker = s.get(Profile, pa.id)
    others = match_service._approved_profiles(s)
    cands = match_service.candidate_offerings_for_need(need, seeker, others)
    # Zonder discipline-boost zou de woord-overlap (workshop↔sessie, geen) nul zijn →
    # de workshop valt nu tóch binnen de kandidaten dankzij de kind-match.
    assert "Sessie: bouw je eigen assistent" in [o.title for o, _ in cands]
    s.close()


# --------------------------------------------------------------------------- #
# LLM-judge gated                                                             #
# --------------------------------------------------------------------------- #
def test_judge_disabled_returns_empty(SessionTest, seed, monkeypatch):
    from app.config import settings
    from app.models import Need
    from app.services import match_service

    monkeypatch.setattr(settings, "ai_enrich_enabled", False)
    s = SessionTest()
    need = s.get(Need, seed["need"])
    others = match_service._approved_profiles(s)
    cands = match_service.candidate_offerings_for_need(need, need.profile, others)
    assert match_service._judge(need, cands) == []  # geen netwerk-call
    s.close()


# --------------------------------------------------------------------------- #
# Persist + idempotentie                                                      #
# --------------------------------------------------------------------------- #
def _patch_judge(monkeypatch, score=80, reason="past goed"):
    from app.services import match_service

    def fake(need, candidates):
        return (
            [{"offering_id": candidates[0][0].id, "score": score, "reason": reason}]
            if candidates else []
        )

    monkeypatch.setattr(match_service, "_judge", fake)


def test_refresh_persists_match_with_denorm_members(SessionTest, seed, monkeypatch):
    from app.models import Member, MatchStatus
    from app.models.match_suggestion import MatchSuggestion
    from app.services import match_service

    _patch_judge(monkeypatch)
    s = SessionTest()
    alice = s.get(Member, seed["a"])
    n = match_service.refresh_for_member(s, alice)
    s.commit()
    assert n == 1

    rows = s.query(MatchSuggestion).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.offering_id == seed["off_b"]
    assert row.seeker_member_id == seed["a"]
    assert row.maker_member_id == seed["b"]
    assert row.status == MatchStatus.new
    assert row.score == 80
    s.close()


def test_refresh_is_idempotent_and_preserves_dismissed(SessionTest, seed, monkeypatch):
    from app.models import Member, MatchStatus
    from app.models.match_suggestion import MatchSuggestion
    from app.services import match_service

    _patch_judge(monkeypatch)
    s = SessionTest()
    alice = s.get(Member, seed["a"])
    match_service.refresh_for_member(s, alice)
    s.commit()
    row = s.query(MatchSuggestion).one()
    row.status = MatchStatus.dismissed
    s.commit()

    # opnieuw draaien: geen duplicaat, dismissed blijft sticky
    match_service.refresh_for_member(s, alice)
    s.commit()
    rows = s.query(MatchSuggestion).all()
    assert len(rows) == 1
    assert rows[0].status == MatchStatus.dismissed
    s.close()


# --------------------------------------------------------------------------- #
# Weergave: perspectief, ordening, chip                                       #
# --------------------------------------------------------------------------- #
def test_list_for_member_both_perspectives(SessionTest, seed, monkeypatch):
    from app.models import Member
    from app.services import match_service

    _patch_judge(monkeypatch)
    s = SessionTest()
    match_service.refresh_for_member(s, s.get(Member, seed["a"]))
    s.commit()

    alice = s.get(Member, seed["a"])  # zoeker
    bob = s.get(Member, seed["b"])    # maker
    assert len(match_service.list_for_member(s, alice)) == 1
    assert len(match_service.list_for_member(s, bob)) == 1
    assert match_service.count_new_for_member(s, alice) == 1
    assert match_service.count_new_for_member(s, bob) == 1
    s.close()


def test_match_chip_appears_when_new(SessionTest, seed, monkeypatch):
    from app.models import Member
    from app.services import match_service, nudge_service

    _patch_judge(monkeypatch)
    s = SessionTest()
    match_service.refresh_for_member(s, s.get(Member, seed["a"]))
    s.commit()
    alice = s.get(Member, seed["a"])
    chips = nudge_service.select_chips(s, alice)
    assert any(c.kind == "chip_matches" for c in chips)
    s.close()


# --------------------------------------------------------------------------- #
# Surface-loader markeert new → seen                                          #
# --------------------------------------------------------------------------- #
def test_surface_loader_marks_seen(SessionTest, seed, monkeypatch):
    from app.models import Member, MatchStatus
    from app.models.match_suggestion import MatchSuggestion
    from app.routers import concierge as cr
    from app.services import match_service

    _patch_judge(monkeypatch)
    s = SessionTest()
    match_service.refresh_for_member(s, s.get(Member, seed["a"]))
    s.commit()

    tmpl, ctx = cr._load_matches(s, {}, seed["a"], False)
    assert tmpl == "matches/_list.html"
    assert len(ctx["matches"]) == 1
    # na tonen is de match niet meer 'new' (chip loopt leeg)
    assert s.query(MatchSuggestion).one().status == MatchStatus.seen
    assert match_service.count_new_for_member(s, s.get(Member, seed["a"])) == 0
    s.close()


def test_matches_in_surface_registry_and_enum():
    from app.services import concierge_service

    assert "matches" in concierge_service.SURFACE_REGISTRY
    surf = next(t for t in concierge_service.TOOLS if t["name"] == "surface")
    assert "matches" in set(surf["input_schema"]["properties"]["view"]["enum"])


# --------------------------------------------------------------------------- #
# AVG: accountverwijdering ruimt match-suggesties op                          #
# --------------------------------------------------------------------------- #
def test_account_deletion_removes_matches(SessionTest, seed, monkeypatch):
    from app.models import Member
    from app.models.match_suggestion import MatchSuggestion
    from app.services import match_service
    from app.services.account_deletion import delete_member_completely

    _patch_judge(monkeypatch)
    s = SessionTest()
    match_service.refresh_for_member(s, s.get(Member, seed["a"]))
    s.commit()
    assert s.query(MatchSuggestion).count() == 1

    # verwijder de MAKER (Bob) → de suggestie (waar hij maker is) verdwijnt
    delete_member_completely(s, s.get(Member, seed["b"]))
    s.commit()
    assert s.query(MatchSuggestion).count() == 0
    s.close()
