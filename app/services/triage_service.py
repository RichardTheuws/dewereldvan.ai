"""Spam-triage bij registratie (pivot Fase B) — de poort filtert spam, niet mensen.

Beoordeelt ALLEEN of een aanmelding van een echt mens lijkt of van een bot/spam.
Nooit of iemand "goed genoeg" of "relevant genoeg" is — twijfel over relevantie is
GEEN reden om te weren. Twee uitkomsten:

- ``welcome`` — lijkt een echt mens → de route keurt automatisch goed (auto-welkom).
- ``review`` — twijfel/mogelijk spam → blijft pending in de admin-queue (mens beslist).

Er is **geen** auto-``spam``/auto-afwijzing: een AI-vergissing mag nooit een echt mens
buitensluiten (kern van het mandaat). Spam markeren blijft een handmatige admin-actie.

VEILIGE DEFAULTS (KILL-fallback):
- ``AI_ENRICH_ENABLED`` uit → altijd ``review`` (= het gedrag van vóór de pivot: elk
  lid handmatig bekeken). Zo kan de auto-welkom met één env-vlag uit.
- Élke fout (geen key, netwerk, refusal, onverwacht antwoord) → ``review``. Falen leidt
  nooit tot auto-welkom én nooit tot auto-weren — het mens beslist gewoon.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = ["TriageVerdict", "assess_registration"]

_SYSTEM = (
    "Je bent een spam-filter voor dewereldvan.ai, een open platform voor iedereen "
    "met AI-affiniteit: makers, coders, trainers, audio-/video-makers, designers, "
    "onderzoekers, beleidsmakers en nieuwsgierigen — uit ELKE discipline.\n\n"
    "Beoordeel UITSLUITEND of deze aanmelding van een ECHT MENS lijkt, of van een "
    "bot/spam. Beoordeel NOOIT of iemand relevant, serieus of 'goed genoeg' is — "
    "twijfel over relevantie is GEEN reden om te weren. Alleen duidelijke bot-/spam-"
    "signalen tellen: wartaal- of toetsenbord-rommel als naam, een wegwerp-/spam-"
    "e-mailpatroon, een naam en e-mail die kennelijk nergens op slaan, of reclame in "
    "de naam.\n\n"
    "Bij ENIGE twijfel kies je BEKIJK (dan beslist een mens) — nooit automatisch weren. "
    "Een gewoon-ogende naam met een plausibel e-mailadres is WELKOM.\n\n"
    "Antwoord met EXACT één woord op de eerste regel: WELKOM of BEKIJK. Daarna op een "
    "nieuwe regel één korte zin met de reden (in het Nederlands, feitelijk, geen "
    "oordeel over de persoon)."
)


@dataclass(frozen=True)
class TriageVerdict:
    decision: str  # "welcome" | "review"
    reason: str

    @property
    def is_welcome(self) -> bool:
        return self.decision == "welcome"


def _review(reason: str) -> TriageVerdict:
    return TriageVerdict("review", reason)


def assess_registration(name: str, email: str) -> TriageVerdict:
    """Beoordeel een nieuwe aanmelding op spam/bot-waarschijnlijkheid.

    Retourneert altijd een ``TriageVerdict`` — werpt nooit (alle fouten → ``review``).
    """
    if not settings.ai_enrich_enabled:
        return _review("AI-triage uit — handmatig bekeken")

    try:
        import anthropic

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=settings.triage_model,
            max_tokens=120,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Naam: {name}\nE-mail: {email}",
                }
            ],
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            return _review("Triage onbeslist — handmatig bekeken")

        parts: list[str] = []
        for block in getattr(resp, "content", None) or []:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(text)
        raw = "".join(parts).strip()
        if not raw:
            return _review("Triage gaf geen antwoord — handmatig bekeken")

        first, _, rest = raw.partition("\n")
        reason = (rest.strip() or first.strip())[:480]
        # Alleen een EXPLICIETE WELKOM leidt tot auto-welkom; al het andere (incl.
        # onverwachte output) valt veilig terug op review. Nooit auto-weren.
        if first.strip().upper().startswith("WELKOM"):
            return TriageVerdict("welcome", reason or "Lijkt een echt mens")
        return _review(reason or "Twijfel — handmatig bekeken")
    except Exception:  # noqa: BLE001 — triage mag registratie nooit breken
        logger.info("Spam-triage overgeslagen (Claude niet beschikbaar) → review.")
        return _review("Triage niet beschikbaar — handmatig bekeken")
