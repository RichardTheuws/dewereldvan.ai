"""visitor_spend metering — kostberekening, tellingen, week-som en cache-lookup.

SQLite in-memory via de ``db``-fixture. Geen netwerk; we boeken rijen direct met
``record_spend`` en passen ``now`` aan om vensters deterministisch te raken.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.config import settings
from app.services import visitor_spend


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


def test_compute_cost_micros_uses_model_price():
    # 1M input + 1M output → input-prijs + output-prijs, in micro-euro.
    cost = visitor_spend.compute_cost_micros(1_000_000, 1_000_000)
    expected_eur = (
        settings.ai_price_input_eur_per_mtok + settings.ai_price_output_eur_per_mtok
    )
    assert cost == round(expected_eur * 1_000_000)


def test_record_spend_cost_from_tokens(db):
    row = _seed(db, input_tokens=12_000, output_tokens=600)
    expected = visitor_spend.compute_cost_micros(12_000, 600)
    assert row.cost_eur_micros == expected
    assert row.cost_eur_micros > 0


def test_cache_hit_costs_zero(db):
    row = _seed(db, input_tokens=12_000, output_tokens=600, cache_hit=True)
    assert row.cache_hit is True
    assert row.cost_eur_micros == 0


def test_week_spend_sums_only_current_week(db):
    now = datetime(2026, 6, 18, 12, 0, 0)  # donderdag
    # In de week: maandag deze week.
    monday = now - timedelta(days=now.weekday())
    in_week = _seed(db, input_tokens=1_000_000, output_tokens=0)
    in_week.created_at = monday + timedelta(hours=1)
    # Vorige week (mag NIET meetellen).
    old = _seed(db, input_tokens=1_000_000, output_tokens=0)
    old.created_at = monday - timedelta(days=2)
    db.flush()

    total = visitor_spend.week_spend_eur(db, now)
    # Alleen de in-week-rij (1M input tokens) telt.
    assert total == visitor_spend.compute_cost_micros(1_000_000, 0) / 1_000_000


def test_calls_today_for_visitor_window(db):
    now = datetime(2026, 6, 18, 12, 0, 0)
    recent = _seed(db, visitor_id="v1")
    recent.created_at = now - timedelta(hours=1)
    stale = _seed(db, visitor_id="v1")
    stale.created_at = now - timedelta(hours=30)  # buiten 24u
    db.flush()
    assert visitor_spend.calls_today_for_visitor(db, "v1", now) == 1


def test_seconds_since_last_call(db):
    now = datetime(2026, 6, 18, 12, 0, 0)
    assert visitor_spend.seconds_since_last_call(db, "v1", now) is None
    row = _seed(db, visitor_id="v1")
    row.created_at = now - timedelta(seconds=10)
    db.flush()
    elapsed = visitor_spend.seconds_since_last_call(db, "v1", now)
    assert elapsed is not None and 9 <= elapsed <= 11


def test_cache_lookup_respects_ttl(db):
    now = datetime(2026, 6, 18, 12, 0, 0)
    fresh = _seed(db, prompt_hash="abc")
    fresh.created_at = now - timedelta(hours=1)
    db.flush()
    assert visitor_spend.cache_lookup(db, "abc", now) is not None

    # Buiten de TTL → geen hit.
    expired_at = now - timedelta(hours=settings.visitor_ai_prompt_cache_ttl_hours + 1)
    fresh.created_at = expired_at
    db.flush()
    assert visitor_spend.cache_lookup(db, "abc", now) is None
