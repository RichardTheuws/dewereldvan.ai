"""Magic-link issue / verify / single-use-reuse / expiry (service + DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models import MagicLinkToken, MemberStatus
from app.security import hash_token
from app.services.magic_link import (
    RateLimitExceeded,
    VerifyStatus,
    issue_link,
    verify_link,
)

NOW = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def test_issue_creates_unused_hashed_token(db, make_member):
    member = make_member(email="a@example.com", status=MemberStatus.approved)
    issued = issue_link(db, member, now=NOW)

    row = db.get(MagicLinkToken, issued.token.id)
    assert row.used_at is None
    assert row.member_id == member.id
    # Raw token is NEVER stored; only its salted hash.
    assert row.token_hash != issued.raw_token
    assert row.token_hash == hash_token(issued.raw_token)
    # Expiry is now + TTL (15 min default) — compared naive.
    assert row.expires_at == (NOW + timedelta(minutes=15)).replace(tzinfo=None)


def test_verify_valid_token_consumes_it_and_returns_member(db, make_member):
    member = make_member(email="b@example.com", status=MemberStatus.approved)
    issued = issue_link(db, member, now=NOW)

    result = verify_link(db, issued.raw_token, now=NOW)
    assert result.status is VerifyStatus.ok
    assert result.ok is True
    assert result.member is not None
    assert result.member.id == member.id

    # Single-use marker stamped + login recorded.
    row = db.get(MagicLinkToken, issued.token.id)
    assert row.used_at is not None
    assert member.last_login_at is not None


def test_reuse_of_used_token_is_rejected_cleanly(db, make_member):
    """An already-consumed token cannot grant a second session."""
    member = make_member(email="c@example.com", status=MemberStatus.approved)
    issued = issue_link(db, member, now=NOW)

    first = verify_link(db, issued.raw_token, now=NOW)
    assert first.ok is True

    second = verify_link(db, issued.raw_token, now=NOW + timedelta(seconds=1))
    assert second.status is VerifyStatus.used
    assert second.ok is False
    assert second.member is None  # no silent success


def test_expired_token_is_rejected_cleanly(db, make_member):
    """A token verified after its TTL fails with a distinct 'expired' status."""
    member = make_member(email="d@example.com", status=MemberStatus.approved)
    issued = issue_link(db, member, now=NOW)

    later = NOW + timedelta(minutes=16)  # past the 15-min TTL
    result = verify_link(db, issued.raw_token, now=later)
    assert result.status is VerifyStatus.expired
    assert result.member is None
    # Expired-but-unused token is NOT marked used (clean re-request path).
    row = db.get(MagicLinkToken, issued.token.id)
    assert row.used_at is None


def test_unknown_token_is_rejected(db, make_member):
    make_member(email="e@example.com")
    result = verify_link(db, "this-token-was-never-issued", now=NOW)
    assert result.status is VerifyStatus.invalid
    assert result.member is None


def test_empty_token_is_rejected(db):
    result = verify_link(db, "", now=NOW)
    assert result.status is VerifyStatus.invalid


def test_rate_limit_blocks_excess_requests(db, make_member):
    """At most RATE_LIMIT_MAGIC_PER_HOUR (5) issues per member per hour."""
    member = make_member(email="f@example.com", status=MemberStatus.approved)
    for _ in range(5):
        issue_link(db, member, now=NOW)
    with pytest.raises(RateLimitExceeded):
        issue_link(db, member, now=NOW)
