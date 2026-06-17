"""Token generation/hashing/verification and slug helpers.

Magic-link tokens: the raw token is high-entropy and URL-safe; only its
sha256 hex digest is ever persisted. Functions that deal with time accept an
optional ``now`` so tests can be deterministic.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.config import settings

# Number of random bytes behind a raw token (→ ~43-char URL-safe string).
_TOKEN_BYTES = 32


def utcnow() -> datetime:
    """Timezone-aware current UTC time (single source of 'now')."""
    return datetime.now(UTC)


def naive_utc(value: datetime) -> datetime:
    """Drop tzinfo so we can compare against tz-naive DB columns.

    The model timestamp columns are tz-naive (``TIMESTAMP`` without zone on
    Postgres; SQLite drops tzinfo on round-trip), while ``utcnow()`` is
    tz-aware. We normalize both sides to naive-UTC for safe comparison.
    """
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def generate_token() -> str:
    """Return a fresh high-entropy, URL-safe raw token (never stored)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(raw: str) -> str:
    """Return the sha256 hex digest of a raw token, salted with SECRET_KEY.

    Deterministic: the same raw token always yields the same hash. The raw
    token is not recoverable from the digest.
    """
    salted = f"{settings.secret_key}:{raw}".encode()
    return hashlib.sha256(salted).hexdigest()


def verify_token(raw: str, token_hash: str) -> bool:
    """Constant-time check that ``raw`` hashes to ``token_hash``."""
    return hmac.compare_digest(hash_token(raw), token_hash)


def magic_link_expiry(now: datetime | None = None) -> datetime:
    """Compute the expiry timestamp for a freshly issued magic-link token."""
    now = now or utcnow()
    return now + timedelta(minutes=settings.magic_link_ttl_min)


def pending_expiry(now: datetime | None = None) -> datetime:
    """Compute the pending-account expiry timestamp at registration time."""
    now = now or utcnow()
    return now + timedelta(days=settings.pending_expiry_days)


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Normalize a string to an ASCII, lowercase, hyphenated slug.

    "Jan de Vries" -> "jan-de-vries". Returns "lid" as a safe fallback when
    the input contains no slug-able characters.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", ascii_only.lower()).strip("-")
    return slug or "lid"


def unique_slug(base: str, exists: Callable[[str], bool]) -> str:
    """Return a slug derived from ``base`` that does not yet exist.

    ``exists(candidate)`` must return True when the candidate is already taken.
    Collisions get a numeric suffix: ``jan-de-vries-2``, ``-3``, ...
    """
    root = slugify(base)
    if not exists(root):
        return root
    n = 2
    while exists(f"{root}-{n}"):
        n += 1
    return f"{root}-{n}"
