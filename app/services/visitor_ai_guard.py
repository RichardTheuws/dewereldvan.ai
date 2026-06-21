"""visitor_ai_guard — de 9-staps gate vóór én ná élke betaalde niet-lid-call.

Eén plek die beslist of een gewone bezoeker een betaalde Opus-call MAG (stappen
1-6, ``check``) en die ná de call de echte kost boekt + drempels checkt (stappen
8-9, ``record_after_call``). Stap 7 (de Anthropic-call zelf) zit hier bewust NIET
in — dat is Fase 2; de gate beslist alleen of er gebeld mag worden.

Gate-volgorde (doc §4.3):
  1. Turnstile server-side valideren        → faalt? reason 'turnstile'
  2. anti-burst (< min_seconds)?             → ja? reason 'burst'
  3. prompt_hash in cache (< TTL)?           → ja? reason 'cache' + cached rij
  4. per-visitor daglimiet (rij-tel 24u)?    → vol? reason 'day_visitor'
  5. per-IP daglimiet (rij-tel 24u)?         → vol? reason 'day_ip'
  6. GLOBALE WEEKCAP: som + voorschat > cap? → over? reason 'weekcap'
  7. → call uitvoeren                        (Fase 2, niet hier)
  8. → echte usage boeken                    (record_after_call)
  9. → drempel-check 80%/100% → Telegram?    (record_after_call, idempotent/week)

Stappen 1-6 zijn goedkoop (cookie-check + een paar COUNT/SUM-queries) en draaien
vóór de dure call; stap 6 is de wiskundige garantie.

Telegram-ping (stap 9): de gate verstúúrt zelf niets. ``record_after_call`` geeft
een ``threshold_crossed`` ('warn' bij 80%, 'cap' bij 100%) terug zodra de weeksom
nét een drempel passeert (de vorige som lag eronder, de nieuwe erboven →
idempotent per ISO-week, want het kruispunt gebeurt per week precies één keer).
De Fase-2-route beslist op die signaalwaarde om ``telegram_service.send_message``
aan te roepen. Bewust ontkoppeld: de meter-laag blijft side-effect-vrij en
testbaar zonder netwerk, en een falende Telegram-call kan de boeking nooit raken.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AiSpendLog
from app.security import utcnow
from app.services import turnstile_service, visitor_spend


@dataclass(frozen=True)
class GuardDecision:
    """Uitkomst van de pre-call gate.

    ``reason`` is machine-leesbaar: 'ok' | 'turnstile' | 'burst' | 'cache' |
    'day_visitor' | 'day_ip' | 'weekcap'. Bij 'cache' draagt ``cache_hit`` de
    cached rij (serveer die, geen nieuwe call). Bij elke andere niet-'ok'-reason
    is er geen call gedaan en geen spend geboekt.
    """

    allowed: bool
    reason: str
    cache_hit: AiSpendLog | None = None


@dataclass(frozen=True)
class RecordResult:
    """Uitkomst van het boeken ná de call.

    ``row`` is de geboekte ``ai_spend_log``-rij. ``threshold_crossed`` is None,
    'warn' (≥80% net gepasseerd) of 'cap' (≥100% net gepasseerd) → signaal voor
    de Fase-2-route om een Telegram-ping te sturen (idempotent per ISO-week).
    """

    row: AiSpendLog
    threshold_crossed: str | None = None


def check(
    db: Session,
    *,
    visitor_id: str,
    ip: str,
    concept: str,
    prompt_hash: str,
    turnstile_token: str | None,
    now: datetime | None = None,
) -> GuardDecision:
    """Beslis of deze bezoeker een betaalde call MAG (gate-stappen 1-6)."""
    now = now or utcnow()

    # Stap 1 — Turnstile server-side valideren (en de veilige default: zonder
    # geconfigureerde key is het hele pad uit → 'turnstile', geen call).
    if not turnstile_service.verify(turnstile_token, ip):
        return GuardDecision(allowed=False, reason="turnstile")

    # Stap 2 — anti-burst: te kort na de vorige call van deze bezoeker?
    elapsed = visitor_spend.seconds_since_last_call(db, visitor_id, now)
    if elapsed is not None and elapsed < settings.visitor_ai_min_seconds_between_calls:
        return GuardDecision(allowed=False, reason="burst")

    # Stap 3 — identieke prompt binnen TTL? Serveer uit cache (€0, geen call).
    cached = visitor_spend.cache_lookup(db, prompt_hash, now)
    if cached is not None:
        return GuardDecision(allowed=False, reason="cache", cache_hit=cached)

    # Stap 4 — per-bezoeker daglimiet (rij-tel 24u).
    if (
        visitor_spend.calls_today_for_visitor(db, visitor_id, now)
        >= settings.visitor_ai_calls_per_day
    ):
        return GuardDecision(allowed=False, reason="day_visitor")

    # Stap 5 — per-IP daglimiet (grover vangnet voor cookie-wissers).
    if (
        visitor_spend.calls_today_for_ip(db, ip, now)
        >= settings.visitor_ai_calls_per_ip_per_day
    ):
        return GuardDecision(allowed=False, reason="day_ip")

    # Stap 6 — GLOBALE WEEKCAP (de garantie): som(cost) lopende week + conservatieve
    # voorschat > budget? Harde gate vóór de call, geen alert achteraf.
    projected = visitor_spend.week_spend_eur(db, now) + visitor_spend.estimate_cost_eur(
        concept
    )
    if projected > settings.visitor_ai_budget_eur_per_week:
        return GuardDecision(allowed=False, reason="weekcap")

    # Stappen 1-6 gehaald → de call MAG (stap 7 = de Anthropic-call, Fase 2).
    return GuardDecision(allowed=True, reason="ok")


def record_after_call(
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
    now: datetime | None = None,
) -> RecordResult:
    """Boek de echte usage (stap 8) + drempel-check (stap 9).

    Bepaalt de weeksom **vóór** de boeking, boekt de rij, en kijkt of de som nét
    een drempel (80% / 100% van de weekcap) heeft gepasseerd. Omdat per ISO-week
    elk kruispunt precies één keer gebeurt (de vorige som lag eronder, de nieuwe
    erboven), is het signaal vanzelf idempotent binnen de week — geen extra
    markeringstabel nodig.
    """
    now = now or utcnow()
    budget = settings.visitor_ai_budget_eur_per_week
    before = visitor_spend.week_spend_eur(db, now)

    row = visitor_spend.record_spend(
        db,
        visitor_id=visitor_id,
        ip=ip,
        concept=concept,
        prompt_hash=prompt_hash,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_hit=cache_hit,
        response_text=response_text,
    )

    after = visitor_spend.week_spend_eur(db, now)
    crossed = _threshold_crossed(before, after, budget)
    return RecordResult(row=row, threshold_crossed=crossed)


def _threshold_crossed(before: float, after: float, budget: float) -> str | None:
    """Geef 'cap'/'warn'/None: welke drempel de weeksom nét passeerde.

    'cap' (100%) heeft voorrang op 'warn' (80%) als beide in één call passeren.
    """
    if budget <= 0:
        return None
    cap = budget
    warn = 0.8 * budget
    if before < cap <= after:
        return "cap"
    if before < warn <= after:
        return "warn"
    return None
