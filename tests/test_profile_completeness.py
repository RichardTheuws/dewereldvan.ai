"""Deterministic profile completeness scoring (0-100)."""

from __future__ import annotations

from app.models import MemberStatus
from app.services.profile_service import (
    add_need,
    add_offering,
    compute_completeness,
    get_or_create_profile,
    recompute_completeness,
    set_tags,
    update_profile,
)


def test_empty_profile_scores_zero(db, make_member):
    owner = make_member(email="empty@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    assert compute_completeness(profile) == 0


def test_bio_only_is_partial(db, make_member):
    owner = make_member(email="bio@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    profile.bio = "Hallo, ik maak dingen."
    score = compute_completeness(profile)
    assert 0 < score < 100


def test_fully_filled_profile_scores_100(db, make_member):
    owner = make_member(email="full@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    update_profile(
        db,
        profile,
        display_name="Vol Profiel",
        bio="Een uitgebreide bio over mezelf.",
        makes_summary="Ik maak keramiek.",
        raw_tags="keramiek, kunst",
    )
    add_offering(db, profile, title="Handgemaakte vaas", description=None)
    add_need(db, profile, title="Zoek een atelierruimte", description=None)
    assert recompute_completeness(profile) == 100


def test_score_is_stored_on_save(db, make_member):
    owner = make_member(email="store@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    update_profile(
        db,
        profile,
        display_name="X",
        bio="bio",
        makes_summary=None,
        raw_tags=None,
    )
    # bio only (25); stored value must match the computed value.
    assert profile.completeness == compute_completeness(profile)


def test_blank_whitespace_does_not_count(db, make_member):
    owner = make_member(email="ws@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    profile.bio = "   "
    set_tags(db, profile, "   ,  ")  # all blanks -> no tags
    assert compute_completeness(profile) == 0
