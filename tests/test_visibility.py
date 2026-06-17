"""Visibility enforcement on read paths + audit on change + delisting."""

from __future__ import annotations

import pytest
from app.models import (
    AuditAction,
    AuditLog,
    MemberStatus,
    Visibility,
)
from app.services.approval import suspend_member
from app.services.profile_service import get_or_create_profile
from app.services.visibility import (
    ConsentRequired,
    can_view,
    change_visibility,
    is_noindex,
)
from sqlalchemy import func, select


def test_new_profile_defaults_to_members_only(db, make_member):
    owner = make_member(email="owner@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    assert profile.visibility is Visibility.members


def test_public_profile_viewable_by_anonymous_and_indexable(db, make_member):
    owner = make_member(email="pub@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    change_visibility(db, profile, Visibility.public, actor=owner, consent=True)

    assert can_view(profile, None) is True  # anonymous allowed
    assert is_noindex(profile) is False  # indexable


def test_members_profile_requires_logged_in_approved_member(db, make_member):
    owner = make_member(email="m1@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)  # default members

    viewer = make_member(email="viewer@example.com", status=MemberStatus.approved)
    pending = make_member(email="pend@example.com", status=MemberStatus.pending)

    assert can_view(profile, None) is False  # anonymous blocked
    assert can_view(profile, pending) is False  # not approved
    assert can_view(profile, viewer) is True  # approved member ok
    assert is_noindex(profile) is True  # members-only => noindex


def test_owner_always_sees_own_profile(db, make_member):
    owner = make_member(email="self@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)  # members-only
    assert can_view(profile, owner) is True


def test_public_to_members_delists_and_audits(db, make_member):
    """public -> members flips enforcement immediately and writes an audit row."""
    owner = make_member(email="flip@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    change_visibility(db, profile, Visibility.public, actor=owner, consent=True)
    assert can_view(profile, None) is True
    assert is_noindex(profile) is False

    changed = change_visibility(db, profile, Visibility.members, actor=owner)
    assert changed is True
    # Delisted: anonymous can no longer view; page becomes noindex.
    assert can_view(profile, None) is False
    assert is_noindex(profile) is True

    rows = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.visibility_changed)
    ).all()
    details = {r.detail for r in rows}
    assert "members->public consent=true" in details
    assert "public->members" in details


def test_going_public_without_consent_is_refused(db, make_member):
    """AVG: publishing personal data requires explicit consent."""
    owner = make_member(email="noconsent@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    with pytest.raises(ConsentRequired):
        change_visibility(db, profile, Visibility.public, actor=owner, consent=False)
    # Refused: still members-only, no consent timestamp, no audit row.
    assert profile.visibility is Visibility.members
    assert profile.consented_public_at is None
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.visibility_changed)
        )
        == 0
    )


def test_going_public_with_consent_records_proof(db, make_member):
    owner = make_member(email="consent@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    changed = change_visibility(
        db, profile, Visibility.public, actor=owner, consent=True
    )
    assert changed is True
    assert profile.visibility is Visibility.public
    assert profile.consented_public_at is not None


def test_suspended_owner_public_profile_is_delisted(db, make_member):
    """A suspended member's public profile must go offline + noindex (AVG)."""
    owner = make_member(email="susp@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)
    change_visibility(db, profile, Visibility.public, actor=owner, consent=True)
    assert can_view(profile, None) is True

    suspend_member(db, owner)
    # No longer world-readable, and not indexable, even though visibility=public.
    assert can_view(profile, None) is False
    assert is_noindex(profile) is True
    # The owner themselves can still see it.
    assert can_view(profile, owner) is True


def test_no_op_visibility_change_writes_no_audit(db, make_member):
    owner = make_member(email="noop@example.com", status=MemberStatus.approved)
    profile = get_or_create_profile(db, owner)  # already members
    changed = change_visibility(db, profile, Visibility.members, actor=owner)
    assert changed is False
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.visibility_changed)
        )
        == 0
    )
