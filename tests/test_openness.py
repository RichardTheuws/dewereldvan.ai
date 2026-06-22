"""Openness — "waar ik voor opensta" (engagement-beschikbaarheid).

Dekt de catalogus-service (normalize/labels/intro/suggestie), de profiel-save
(genormaliseerd, leeg → None) en de /leden "Open voor"-discovery-filter.
"""

from __future__ import annotations

from app.models import OfferingKind, Visibility
from app.services import members_service, openness_service, profile_service


# --------------------------------------------------------------------------- #
# openness_service                                                             #
# --------------------------------------------------------------------------- #
def test_normalize_keeps_valid_dedupes_and_orders():
    # Onbekende slug eruit, dubbel ontdubbeld, canonieke volgorde hersteld.
    out = openness_service.normalize(
        ["samenwerkingen", "INTERVIEWS", "zzz", "interviews"]
    )
    assert out == ["interviews", "samenwerkingen"]


def test_normalize_empty_is_empty_list():
    assert openness_service.normalize(None) == []
    assert openness_service.normalize([]) == []


def test_labels_for_returns_catalog_items_in_order():
    items = openness_service.labels_for(["samenwerkingen", "klantwerk"])
    slugs = [o.slug for o in items]
    assert slugs == ["klantwerk", "samenwerkingen"]  # canonieke volgorde
    assert all(o.icon and o.label and o.blurb for o in items)


def test_intro_for_fills_first_name():
    intro = openness_service.intro_for("interviews", "Mara Visser")
    assert "Mara" in intro and "Visser" not in intro
    # Onbekende slug → lege string (nooit een kapotte prefill).
    assert openness_service.intro_for("zzz", "Mara") == ""


def test_infer_suggested_from_work_items(db, make_member, make_profile, make_offering):
    m = make_member(email="trainer@x.nl", name="Trainer")
    p = make_profile(m, visibility=Visibility.public)
    o = make_offering(p, title="Workshop RAG")
    o.kind = OfferingKind.workshop
    db.flush()
    suggested = openness_service.infer_suggested(p)
    # Een workshop wijst op trainingen + spreken.
    assert "trainingen" in suggested and "spreken" in suggested
    # In canonieke volgorde (spreken vóór... nee: trainingen vóór spreken).
    assert suggested.index("trainingen") < suggested.index("spreken")


# --------------------------------------------------------------------------- #
# profiel-save                                                                 #
# --------------------------------------------------------------------------- #
def test_update_profile_stores_normalized_open_to(db, make_member, make_profile):
    m = make_member(email="o@x.nl", name="Open")
    p = make_profile(m)
    profile_service.update_profile(
        db, p, display_name="Open", bio=None, makes_summary=None, raw_tags=None,
        open_to=["interviews", "zzz", "samenwerkingen"],
    )
    assert p.open_to == ["interviews", "samenwerkingen"]  # invalide eruit, geordend


def test_update_profile_empty_open_to_is_none(db, make_member, make_profile):
    m = make_member(email="n@x.nl", name="Niets")
    p = make_profile(m)
    p.open_to = ["interviews"]
    db.flush()
    profile_service.update_profile(
        db, p, display_name="Niets", bio=None, makes_summary=None, raw_tags=None,
        open_to=[],
    )
    assert p.open_to is None  # leeg → None (geen lege lijst)


# --------------------------------------------------------------------------- #
# /leden discovery-filter                                                      #
# --------------------------------------------------------------------------- #
def test_list_public_profiles_filter_open_to(db, make_member, make_profile):
    a = make_profile(make_member(email="a@x.nl", name="A"), visibility=Visibility.public)
    a.open_to = ["interviews", "samenwerkingen"]
    b = make_profile(make_member(email="b@x.nl", name="B"), visibility=Visibility.public)
    b.open_to = ["klantwerk"]
    make_profile(make_member(email="c@x.nl", name="C"), visibility=Visibility.public)  # open_to leeg
    db.flush()

    interviews = members_service.list_public_profiles(db, open_to="interviews")
    assert [p.display_name for p in interviews] == ["A"]
    klant = members_service.list_public_profiles(db, open_to="klantwerk")
    assert [p.display_name for p in klant] == ["B"]
    # Onbekende/lege filter → genegeerd (alle drie de publieke profielen).
    assert len(members_service.list_public_profiles(db, open_to="zzz")) == 3
    assert len(members_service.list_public_profiles(db, open_to="")) == 3
