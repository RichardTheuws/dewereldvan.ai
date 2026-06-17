"""Open registration: idempotent duplicates, normalization, pending expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models import Member, MemberStatus
from app.services.registration import (
    RegistrationRateLimited,
    get_member_by_email,
    purge_expired_pending,
    register_member,
)
from sqlalchemy import func, select

NOW = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def test_new_email_creates_pending_member_with_expiry(db):
    result = register_member(db, name="Nieuw Lid", email="new@example.com", now=NOW)
    assert result.created is True
    m = result.member
    assert m.status is MemberStatus.pending
    # pending_expires_at = now + 14 days (default), stored naive.
    assert m.pending_expires_at == (NOW + timedelta(days=14)).replace(tzinfo=None)


def test_duplicate_registration_is_idempotent(db):
    """Registering the same e-mail twice never creates a second row."""
    first = register_member(db, name="Jan", email="dup@example.com", now=NOW)
    assert first.created is True

    second = register_member(db, name="Jan Anders", email="dup@example.com", now=NOW)
    assert second.created is False  # idempotent, no leak about existence
    assert second.member.id == first.member.id

    count = db.scalar(
        select(func.count()).select_from(Member).where(Member.email == "dup@example.com")
    )
    assert count == 1


def test_duplicate_is_case_insensitive(db):
    register_member(db, name="A", email="Case@Example.com", now=NOW)
    again = register_member(db, name="B", email="case@example.com", now=NOW)
    assert again.created is False
    count = db.scalar(select(func.count()).select_from(Member))
    assert count == 1


def test_email_is_lowercased_on_store(db):
    result = register_member(db, name="A", email="MiXeD@Example.COM", now=NOW)
    assert result.member.email == "mixed@example.com"
    assert get_member_by_email(db, "MIXED@EXAMPLE.COM") is not None


def test_registration_is_rate_limited_per_ip(db):
    """At most rate_limit_register_per_hour (5) new registrations per IP/hour."""
    ip = "203.0.113.7"
    for i in range(5):
        register_member(db, name="A", email=f"flood{i}@example.com", requested_ip=ip, now=NOW)
    with pytest.raises(RegistrationRateLimited):
        register_member(db, name="A", email="flood-over@example.com", requested_ip=ip, now=NOW)
    # The blocked e-mail was never inserted.
    assert get_member_by_email(db, "flood-over@example.com") is None


def test_rate_limit_does_not_block_other_ips(db):
    ip_a = "203.0.113.8"
    for i in range(5):
        register_member(db, name="A", email=f"a{i}@example.com", requested_ip=ip_a, now=NOW)
    # A different IP is unaffected.
    result = register_member(
        db, name="B", email="other-ip@example.com", requested_ip="203.0.113.9", now=NOW
    )
    assert result.created is True


def test_idempotent_repeat_not_rate_limited(db):
    """Re-submitting the SAME e-mail is idempotent and never counts against the cap."""
    ip = "203.0.113.10"
    register_member(db, name="A", email="dup-ip@example.com", requested_ip=ip, now=NOW)
    for _ in range(10):
        res = register_member(db, name="A", email="dup-ip@example.com", requested_ip=ip, now=NOW)
        assert res.created is False


def test_purge_expired_pending_removes_only_stale_pending(db):
    # Stale pending (expired yesterday) -> removed.
    stale = register_member(db, name="Stale", email="stale@example.com", now=NOW)
    stale.member.pending_expires_at = (NOW - timedelta(days=1)).replace(tzinfo=None)
    # Fresh pending (expires in future) -> kept.
    register_member(db, name="Fresh", email="fresh@example.com", now=NOW)
    # Approved member with a past pending_expires_at -> never touched.
    approved = register_member(db, name="Approved", email="appr@example.com", now=NOW)
    approved.member.status = MemberStatus.approved
    approved.member.pending_expires_at = (NOW - timedelta(days=5)).replace(tzinfo=None)
    db.flush()

    removed = purge_expired_pending(db, now=NOW)
    assert removed == 1

    remaining = {m.email for m in db.scalars(select(Member)).all()}
    assert "stale@example.com" not in remaining
    assert "fresh@example.com" in remaining
    assert "appr@example.com" in remaining
