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
from typing import TYPE_CHECKING

from itsdangerous import BadSignature, URLSafeSerializer

from app.config import settings

if TYPE_CHECKING:
    from fastapi import Request, Response

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


# --- Echte client-IP achter de Cloudflare Tunnel ------------------------------
def client_ip(request: Request) -> str:
    """Geef de echte client-IP, niet de (ene) upstream-Tunnel-IP.

    Achter de Cloudflare Tunnel is ``request.client.host`` altijd het ene
    upstream-IP → waardeloos voor per-IP-limieten. Cloudflare zet ``CF-Connecting-IP``
    op de echte bezoeker-IP, en de Tunnel is de enige weg naar binnen, dus de
    bezoeker kan die header niet spoofen (doc §2.1).

    Faal-veilig (doc §risico 3): ontbreekt de header, val terug op
    ``request.client.host``; ontbreekt ook dat → ``"unknown"`` (behandeld als
    één emmer; de weekcap blijft de garantie). Nooit crashen op een ontbrekende
    header.
    """
    header = request.headers.get("CF-Connecting-IP")
    if header and header.strip():
        return header.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


# --- visitor_id: server-gezette, signed cookie (telunit voor de daglimiet) ----
# Naam van de signed cookie die de bezoeker over requests heen identificeert.
VISITOR_COOKIE = "dwv_vid"
# Aparte salt zodat een visitor-cookie nooit met de sessie-cookie te verwarren is.
_VISITOR_SALT = "dwv-visitor-id"
# 180 dagen — de cookie hoeft alleen lang genoeg te leven om de daglimiet-emmer
# stabiel te houden; geen gevoelige data (alleen een opaque id).
_VISITOR_MAX_AGE = 60 * 60 * 24 * 180


def _visitor_serializer() -> URLSafeSerializer:
    """Signer met dezelfde ``secret_key``-mechaniek als de sessie-cookie."""
    return URLSafeSerializer(settings.secret_key, salt=_VISITOR_SALT)


def _read_visitor_id(request: Request) -> str | None:
    """Lees + verifieer de signed visitor-cookie; None bij afwezig/ongeldig."""
    raw = request.cookies.get(VISITOR_COOKIE)
    if not raw:
        return None
    try:
        value = _visitor_serializer().loads(raw)
    except BadSignature:
        return None
    return value if isinstance(value, str) and value else None


def get_or_set_visitor_id(request: Request, response: Response) -> str:
    """Geef de bezoeker-id uit de signed cookie, of mint+zet een verse.

    De id is een opaque, willekeurige token (geen PII). Bij een geldige cookie
    hergebruiken we 'm (stabiele daglimiet-emmer); ontbreekt of klopt de
    handtekening niet, dan minten we een nieuwe en zetten 'm als signed,
    HttpOnly, SameSite=Lax cookie op het meegegeven ``response``.
    """
    existing = _read_visitor_id(request)
    if existing is not None:
        return existing
    visitor_id = secrets.token_urlsafe(16)
    response.set_cookie(
        VISITOR_COOKIE,
        _visitor_serializer().dumps(visitor_id),
        max_age=_VISITOR_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return visitor_id
