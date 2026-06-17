"""Magic-link service — issue and verify single-use, hashed, TTL'd tokens.

Edge cases handled here (PRD §4):
- Single use: a token's ``used_at`` is stamped on first successful verify;
  re-verifying it fails cleanly (no session, clear error path).
- Expiry: tokens past ``expires_at`` fail cleanly (re-request path).
- Unknown/garbage token: fails cleanly.
- Rate limit: at most ``RATE_LIMIT_MAGIC_PER_HOUR`` issues per member per hour.

Raw tokens are never persisted — only their salted sha256 hash. The raw token
is returned once (so the caller can e-mail the link) and then discarded.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import MagicLinkToken, Member
from app.security import (
    generate_token,
    hash_token,
    magic_link_expiry,
    naive_utc,
    utcnow,
)


class VerifyStatus(str, enum.Enum):
    ok = "ok"
    invalid = "invalid"  # unknown token / hash mismatch
    expired = "expired"
    used = "used"  # already consumed (reuse attempt)


@dataclass(frozen=True)
class IssuedLink:
    raw_token: str  # to embed in the e-mailed URL; never stored
    token: MagicLinkToken


@dataclass(frozen=True)
class VerifyResult:
    status: VerifyStatus
    member: Member | None = None

    @property
    def ok(self) -> bool:
        return self.status is VerifyStatus.ok


class RateLimitExceeded(RuntimeError):
    """Raised when a member requests too many magic links within the window."""


def _recent_count(db: Session, member_id: int, now: datetime) -> int:
    window_start = naive_utc(now) - timedelta(hours=1)
    return (
        db.scalar(
            select(func.count())
            .select_from(MagicLinkToken)
            .where(
                MagicLinkToken.member_id == member_id,
                MagicLinkToken.created_at >= window_start,
            )
        )
        or 0
    )


def issue_link(
    db: Session,
    member: Member,
    *,
    requested_ip: str | None = None,
    now: datetime | None = None,
) -> IssuedLink:
    """Create a fresh magic-link token for ``member`` and return the raw token.

    Raises ``RateLimitExceeded`` if the member exceeded the per-hour budget.
    """
    now = now or utcnow()
    if _recent_count(db, member.id, now) >= settings.rate_limit_magic_per_hour:
        raise RateLimitExceeded()

    raw = generate_token()
    token = MagicLinkToken(
        member_id=member.id,
        token_hash=hash_token(raw),
        # Store naive-UTC to match the tz-naive column (round-trip stable).
        expires_at=naive_utc(magic_link_expiry(now)),
        requested_ip=requested_ip,
    )
    db.add(token)
    db.flush()
    return IssuedLink(raw_token=raw, token=token)


def verify_link(
    db: Session,
    raw_token: str,
    *,
    now: datetime | None = None,
) -> VerifyResult:
    """Verify a raw magic-link token and, on success, consume it (single-use).

    Returns a ``VerifyResult`` describing exactly why verification failed so the
    route can show a clean re-request path — never a silent failure.
    """
    now = now or utcnow()
    if not raw_token:
        return VerifyResult(VerifyStatus.invalid)

    token_hash = hash_token(raw_token)
    now_naive = naive_utc(now)

    token = db.scalar(
        select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
    )
    if token is None:
        return VerifyResult(VerifyStatus.invalid)
    if token.used_at is not None:
        return VerifyResult(VerifyStatus.used)
    if naive_utc(token.expires_at) <= now_naive:
        return VerifyResult(VerifyStatus.expired)

    # Consume atomically: only the request that flips used_at from NULL wins.
    # A concurrent verify of the same token (e-mail prefetch, double-submit)
    # finds rowcount==0 here and is reported as already-used — never a second
    # session from one single-use link.
    result = db.execute(
        update(MagicLinkToken)
        .where(
            MagicLinkToken.token_hash == token_hash,
            MagicLinkToken.used_at.is_(None),
        )
        .values(used_at=now_naive)
    )
    if result.rowcount == 0:
        return VerifyResult(VerifyStatus.used)

    member = db.get(Member, token.member_id)
    if member is None:
        return VerifyResult(VerifyStatus.invalid)
    member.last_login_at = now_naive
    db.flush()
    return VerifyResult(VerifyStatus.ok, member=member)
