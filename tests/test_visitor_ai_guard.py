"""visitor_ai_guard — de 9-staps gate (stappen 1-6 ``check``, 8-9 ``record``).

Geen netwerk: Turnstile wordt gemockt via ``monkeypatch`` op
``turnstile_service.verify``/``configured``. SQLite in-memory via ``db``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.services import turnstile_service, visitor_ai_guard, visitor_spend

NOW = datetime(2026, 6, 18, 12, 0, 0)  # vaste donderdag


@pytest.fixture
def turnstile_ok(monkeypatch):
    """Doe alsof Turnstile geconfigureerd is en elk token geldig is."""
    monkeypatch.setattr(turnstile_service, "configured", lambda: True)
    monkeypatch.setattr(turnstile_service, "verify", lambda token, ip=None: True)


def _seed(db, **overrides):
    base = dict(
        visitor_id="v1",
        ip="1.2.3.4",
        concept="url_card",
        prompt_hash="h",
        input_tokens=0,
        output_tokens=0,
    )
    base.update(overrides)
    return visitor_spend.record_spend(db, **base)


def _check(db, **overrides):
    args = dict(
        visitor_id="v1",
        ip="1.2.3.4",
        concept="url_card",
        prompt_hash="prompt-x",
        turnstile_token="tok",
        now=NOW,
    )
    args.update(overrides)
    return visitor_ai_guard.check(db, **args)


# --- Stap 1: Turnstile --------------------------------------------------------
def test_turnstile_unconfigured_denies(db, monkeypatch):
    # Veilige default: geen secret-key → verify() is altijd False → 'turnstile'.
    monkeypatch.setattr(settings, "turnstile_secret_key", None)
    decision = _check(db)
    assert decision.allowed is False
    assert decision.reason == "turnstile"


def test_turnstile_valid_passes(db, turnstile_ok):
    decision = _check(db)
    assert decision.allowed is True
    assert decision.reason == "ok"


# --- Stap 2: anti-burst -------------------------------------------------------
def test_burst_within_min_seconds(db, turnstile_ok):
    row = _seed(db, visitor_id="v1")
    row.created_at = NOW - timedelta(
        seconds=settings.visitor_ai_min_seconds_between_calls - 5
    )
    db.flush()
    decision = _check(db)
    assert decision.allowed is False
    assert decision.reason == "burst"


# --- Stap 3: cache ------------------------------------------------------------
def test_cache_hit_returns_cached_row(db, turnstile_ok):
    cached = _seed(db, prompt_hash="prompt-x", visitor_id="other")
    cached.created_at = NOW - timedelta(hours=1)
    db.flush()
    decision = _check(db, prompt_hash="prompt-x")
    assert decision.allowed is False
    assert decision.reason == "cache"
    assert decision.cache_hit is not None
    assert decision.cache_hit.id == cached.id


# --- Stap 4: per-visitor daglimiet -------------------------------------------
def test_day_visitor_limit(db, turnstile_ok, monkeypatch):
    monkeypatch.setattr(settings, "visitor_ai_calls_per_day", 3)
    # 3 calls van v1 binnen 24u → de 4e moet 'day_visitor' geven.
    for i in range(3):
        r = _seed(db, visitor_id="v1", prompt_hash=f"seed-{i}")
        r.created_at = NOW - timedelta(hours=2, minutes=i)
    db.flush()
    decision = _check(db)  # nieuwe prompt-hash → geen cache
    assert decision.allowed is False
    assert decision.reason == "day_visitor"


# --- Stap 5: per-IP daglimiet -------------------------------------------------
def test_day_ip_limit(db, turnstile_ok, monkeypatch):
    monkeypatch.setattr(settings, "visitor_ai_calls_per_day", 100)  # niet de blocker
    monkeypatch.setattr(settings, "visitor_ai_calls_per_ip_per_day", 2)
    # 2 calls vanaf hetzelfde IP, maar verschillende visitors (omzeilt visitor-cap).
    for i in range(2):
        r = _seed(db, visitor_id=f"vv{i}", ip="9.9.9.9", prompt_hash=f"ipseed-{i}")
        r.created_at = NOW - timedelta(hours=1, minutes=i)
    db.flush()
    decision = _check(db, visitor_id="fresh", ip="9.9.9.9")
    assert decision.allowed is False
    assert decision.reason == "day_ip"


# --- Stap 6: globale weekcap --------------------------------------------------
def test_weekcap_blocks(db, turnstile_ok, monkeypatch):
    # Budget laag → som + voorschat overschrijdt direct.
    monkeypatch.setattr(settings, "visitor_ai_budget_eur_per_week", 0.05)
    decision = _check(db, concept="url_card")  # voorschat 0.08 > 0.05
    assert decision.allowed is False
    assert decision.reason == "weekcap"


def test_weekcap_counts_only_current_week(db, turnstile_ok, monkeypatch):
    monkeypatch.setattr(settings, "visitor_ai_budget_eur_per_week", 0.10)
    # Een dure rij in een vorige week mag de gate NIET dichtduwen.
    monday = NOW - timedelta(days=NOW.weekday())
    old = _seed(db, input_tokens=10_000_000, output_tokens=0, prompt_hash="old")
    old.created_at = monday - timedelta(days=3)
    db.flush()
    decision = _check(db, concept="url_card")  # 0 + 0.08 < 0.10
    assert decision.allowed is True
    assert decision.reason == "ok"


# --- Stap 8/9: record_after_call + drempel ------------------------------------
def test_record_after_call_books_real_usage(db):
    result = visitor_ai_guard.record_after_call(
        db,
        visitor_id="v1",
        ip="1.2.3.4",
        concept="url_card",
        prompt_hash="p",
        input_tokens=12_000,
        output_tokens=600,
        now=NOW,
    )
    assert result.row.cost_eur_micros == visitor_spend.compute_cost_micros(12_000, 600)
    assert result.threshold_crossed is None


def test_threshold_warn_crossed(db, monkeypatch):
    # Budget €1; net onder 80% (0.79) staan, dan een call die over 0.80 tilt.
    monkeypatch.setattr(settings, "visitor_ai_budget_eur_per_week", 1.0)
    seed = _seed(db, input_tokens=0, output_tokens=0)
    # Forceer een weeksom net onder de warn-drempel via een grote input.
    monday = NOW - timedelta(days=NOW.weekday())
    seed.created_at = monday + timedelta(hours=1)
    # 0.79 euro = 790_000 micros. Reken terug naar tokens via input-prijs.
    seed.cost_eur_micros = 790_000
    db.flush()

    result = visitor_ai_guard.record_after_call(
        db,
        visitor_id="v1",
        ip="1.2.3.4",
        concept="url_card",
        prompt_hash="p2",
        input_tokens=0,
        output_tokens=0,
        cache_hit=False,
        now=NOW,
    )
    # We boeken een rij die €0 kost (0 tokens) → som blijft 0.79, geen kruising.
    assert result.threshold_crossed is None

    # Nu een rij die de som over 0.80 tilt (≈ €0.05 erbij).
    result2 = visitor_ai_guard.record_after_call(
        db,
        visitor_id="v1",
        ip="1.2.3.4",
        concept="url_card",
        prompt_hash="p3",
        input_tokens=20_000,  # ~0.093 euro
        output_tokens=0,
        now=NOW,
    )
    assert result2.threshold_crossed == "warn"


# --- Leden tellen niet mee ----------------------------------------------------
def test_member_action_does_not_move_week_sum(db, make_member):
    # Een lid-actie raakt visitor_spend NIET aan: de weeksom blijft 0 zolang er
    # geen visitor-call wordt geboekt. (record_spend is het enige schrijfpad en
    # wordt op het lid-pad nooit aangeroepen.)
    member = make_member(email="lid@x.nl")
    assert member.id is not None
    assert visitor_spend.week_spend_eur(db, NOW) == 0.0
    # Een echte visitor-call beweegt de som wél.
    visitor_ai_guard.record_after_call(
        db,
        visitor_id="v1",
        ip="1.2.3.4",
        concept="url_card",
        prompt_hash="p",
        input_tokens=12_000,
        output_tokens=600,
        now=NOW,
    )
    assert visitor_spend.week_spend_eur(db, NOW) > 0.0
