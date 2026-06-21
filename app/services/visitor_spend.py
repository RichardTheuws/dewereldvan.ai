"""Visitor-spend metering — boeken, tellen en kosten-rekenen op ``ai_spend_log``.

De meter-laag onder de gate (``visitor_ai_guard``). Eén append-only tabel draagt
elke betaalde niet-lid-call; de tel-functies spiegelen het rij-tel/SUM-patroon van
``magic_link._recent_count`` (glijdend venster met ``naive_utc(now) - timedelta``).

Kosten worden **per call uit de echte token-usage** berekend en bevroren in
``cost_eur_micros`` (zodat een latere prijswijziging oude rijen niet vervalst).
Bij een cache-hit kost de rij €0 (telt als call, niet als uitgave). Léden-acties
roepen dit nooit aan → ze tellen per definitie niet mee in de €50.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AiSpendLog
from app.security import naive_utc, utcnow

# Geldige concept-waarden (geen DB-enum; deze lijst is de bron).
CONCEPTS = ("url_card", "concierge_q", "tool_explain")

# Bovengrens-planningswaarden per concept (doc §3) — gebruikt als conservatieve
# voorschat in de weekcap-gate (we corrigeren ná de call op echte usage).
_ESTIMATE_EUR: dict[str, float] = {
    "url_card": 0.08,
    "concierge_q": 0.12,
    "tool_explain": 0.05,
}

_MICROS_PER_EUR = 1_000_000


def estimate_cost_eur(concept: str) -> float:
    """Conservatieve voorschat (bovengrens) van de kost van één call, in euro."""
    return _ESTIMATE_EUR.get(concept, max(_ESTIMATE_EUR.values()))


def compute_cost_micros(input_tokens: int, output_tokens: int) -> int:
    """Bereken de kost in micro-euro uit token-usage × modelprijs (config).

    Prijs is per miljoen tokens; afgerond naar hele micro-euro (Integer-kolom →
    geen float-drift in de weeksom).
    """
    eur = (
        input_tokens * settings.ai_price_input_eur_per_mtok
        + output_tokens * settings.ai_price_output_eur_per_mtok
    ) / 1_000_000
    return round(eur * _MICROS_PER_EUR)


def record_spend(
    db: Session,
    *,
    visitor_id: str,
    ip: str,
    concept: str,
    prompt_hash: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit: bool = False,
    response_text: str | None = None,
) -> AiSpendLog:
    """Boek één call als ``ai_spend_log``-rij (append-only) en geef 'm terug.

    Bij ``cache_hit`` is de kost €0 (geserveerd uit cache, geen nieuwe call).
    ``response_text`` bewaart de gegenereerde uitkomst zodat een latere
    identieke-prompt-cache-hit 'm kan hér-serveren. Alleen het visitor-pad
    roept dit aan — léden-acties niet.
    """
    cost = 0 if cache_hit else compute_cost_micros(input_tokens, output_tokens)
    row = AiSpendLog(
        visitor_id=visitor_id,
        ip=ip,
        concept=concept,
        prompt_hash=prompt_hash,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_eur_micros=cost,
        cache_hit=cache_hit,
        response_text=response_text,
    )
    db.add(row)
    db.flush()
    return row


def _iso_week_start(now: datetime) -> datetime:
    """Naive-UTC start (maandag 00:00) van de ISO-week waarin ``now`` valt."""
    base = naive_utc(now)
    monday = base - timedelta(days=base.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def week_spend_eur(db: Session, now: datetime | None = None) -> float:
    """Som van de geboekte kost over de lopende ISO-week, in euro."""
    now = now or utcnow()
    micros = (
        db.scalar(
            select(func.coalesce(func.sum(AiSpendLog.cost_eur_micros), 0)).where(
                AiSpendLog.created_at >= _iso_week_start(now)
            )
        )
        or 0
    )
    return micros / _MICROS_PER_EUR


def week_calls_count(db: Session, now: datetime | None = None) -> int:
    """Aantal geboekte calls (rijen) over de lopende ISO-week — voor de meter."""
    now = now or utcnow()
    return (
        db.scalar(
            select(func.count())
            .select_from(AiSpendLog)
            .where(AiSpendLog.created_at >= _iso_week_start(now))
        )
        or 0
    )


def week_unique_visitors(db: Session, now: datetime | None = None) -> int:
    """Aantal unieke bezoekers (visitor_id) over de lopende ISO-week — meter."""
    now = now or utcnow()
    return (
        db.scalar(
            select(func.count(func.distinct(AiSpendLog.visitor_id))).where(
                AiSpendLog.created_at >= _iso_week_start(now)
            )
        )
        or 0
    )


def calls_today_for_visitor(
    db: Session, visitor_id: str, now: datetime | None = None
) -> int:
    """Aantal calls van deze bezoeker in een glijdend 24u-venster (rij-tel)."""
    now = now or utcnow()
    window_start = naive_utc(now) - timedelta(hours=24)
    return (
        db.scalar(
            select(func.count())
            .select_from(AiSpendLog)
            .where(
                AiSpendLog.visitor_id == visitor_id,
                AiSpendLog.created_at >= window_start,
            )
        )
        or 0
    )


def calls_today_for_ip(db: Session, ip: str, now: datetime | None = None) -> int:
    """Aantal calls vanaf dit IP in een glijdend 24u-venster (grover vangnet)."""
    now = now or utcnow()
    window_start = naive_utc(now) - timedelta(hours=24)
    return (
        db.scalar(
            select(func.count())
            .select_from(AiSpendLog)
            .where(
                AiSpendLog.ip == ip,
                AiSpendLog.created_at >= window_start,
            )
        )
        or 0
    )


def seconds_since_last_call(
    db: Session, visitor_id: str, now: datetime | None = None
) -> float | None:
    """Seconden sinds de vorige call van deze bezoeker, of None (geen eerdere)."""
    now = now or utcnow()
    last = db.scalar(
        select(func.max(AiSpendLog.created_at)).where(
            AiSpendLog.visitor_id == visitor_id
        )
    )
    if last is None:
        return None
    return (naive_utc(now) - naive_utc(last)).total_seconds()


def cache_lookup(
    db: Session, prompt_hash: str, now: datetime | None = None
) -> AiSpendLog | None:
    """Meest recente, niet-verlopen rij voor een identieke prompt (binnen TTL).

    Identieke prompt binnen ``visitor_ai_prompt_cache_ttl_hours`` → geserveerd uit
    cache, geen nieuwe call, telt niet tegen het budget (doc §2.3). Geeft de
    cached rij of None.
    """
    now = now or utcnow()
    ttl_start = naive_utc(now) - timedelta(
        hours=settings.visitor_ai_prompt_cache_ttl_hours
    )
    return db.scalar(
        select(AiSpendLog)
        .where(
            AiSpendLog.prompt_hash == prompt_hash,
            AiSpendLog.created_at >= ttl_start,
        )
        .order_by(AiSpendLog.created_at.desc())
        .limit(1)
    )
