"""Pure token + slug helpers (no DB)."""

from __future__ import annotations

import re

from app.security import (
    generate_token,
    hash_token,
    slugify,
    unique_slug,
    verify_token,
)


def test_generate_token_is_high_entropy_and_url_safe():
    a = generate_token()
    b = generate_token()
    assert a != b  # fresh randomness each call
    assert len(a) >= 32
    # URL-safe base64 alphabet only (token_urlsafe).
    assert re.fullmatch(r"[A-Za-z0-9_-]+", a)


def test_hash_token_is_sha256_hex_and_deterministic():
    raw = generate_token()
    h1 = hash_token(raw)
    h2 = hash_token(raw)
    assert h1 == h2  # same input -> same hash
    assert len(h1) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", h1)


def test_hash_is_not_the_raw_token():
    raw = generate_token()
    h = hash_token(raw)
    # Raw token is not recoverable from / equal to the digest.
    assert raw not in h
    assert h != raw


def test_verify_token_matches_and_rejects():
    raw = generate_token()
    h = hash_token(raw)
    assert verify_token(raw, h) is True
    assert verify_token(raw + "x", h) is False
    assert verify_token("totally-wrong", h) is False


def test_slugify_normalizes_names():
    assert slugify("Jan de Vries") == "jan-de-vries"
    assert slugify("  Ümläut  Náme ") == "umlaut-name"
    assert slugify("!!!") == "lid"  # safe fallback for non-sluggable input


def test_unique_slug_deduplicates_collisions():
    taken = {"jan-de-vries", "jan-de-vries-2"}
    result = unique_slug("Jan de Vries", lambda c: c in taken)
    assert result == "jan-de-vries-3"


def test_unique_slug_returns_root_when_free():
    assert unique_slug("Nieuw Lid", lambda c: False) == "nieuw-lid"
