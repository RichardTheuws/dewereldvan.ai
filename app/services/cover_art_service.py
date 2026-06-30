"""Cover-art-director — een fal.ai-prompt die ECHT dit profiel reflecteert.

De oude ``cover_prompt`` plakte rauwe bio-tekst in een vaste kosmische stijl;
een beeldmodel maakt daar generieke nevels van (proza ≠ visuele scène). Hier
vertaalt één goedkope Claude-call de essentie van dít lid (wat ze maken/doen)
naar een CONCRETE visuele metafoor — bv. voice-agents → "soundwaves dissolving
into constellations" — die we in het vaste kosmische stijl-anker (deep indigo,
glow, geen tekst/gezichten/logo's) zetten. Zo blijft de identiteit gegarandeerd
en wordt het beeld tóch persoonlijk.

Gated op ``ai_enrich_enabled``; bij uit/fout/leeg → terug naar de
deterministische ``cover_prompt`` (bio + tags), zodat de cover altijd werkt.
ANTHROPIC SDK-contract: ``messages.create`` (geen temperature/top_p/etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai import _COVER_STYLE, cover_prompt
from app.config import settings
from app.models import Profile

logger = logging.getLogger(__name__)

_MODEL = settings.anthropic_model
_MAX_TOKENS = 120

# --- Lid-sturing (hero-studio) ------------------------------------------------
# Gecureerde keuzes binnen het kosmische palet — NOOIT een rauwe prompt. Elke
# steer-term wordt ná het stijl-anker + de metafoor toegevoegd, zodat de
# identiteit (geen tekst/gezichten/logo's, deep indigo) leidend blijft.
_ACCENTS: dict[str, str] = {
    "violet": "with a luminous violet accent",
    "cyaan": "with a luminous cyan accent",
    "aurora": "with shifting aurora ribbons of green and magenta",
    "ember": "with warm ember-gold highlights",
}
_ENERGIES: dict[str, str] = {
    "serene": "serene, calm, slow and spacious composition",
    "elektrisch": "electric, dynamic, energetic with crackling motion",
}
_INTENTIE_MAX = 120


@dataclass(frozen=True)
class CoverSteer:
    """Lid-gekozen sturing voor een cover-generatie (alle velden optioneel)."""

    accent: str | None = None  # sleutel uit _ACCENTS
    energie: str | None = None  # sleutel uit _ENERGIES
    motief: str | None = None  # een eigen tag/onderwerp als klemtoon
    intentie: str | None = None  # vrije, korte intentie-regel (gecapt)

    @property
    def is_empty(self) -> bool:
        return not (self.accent or self.energie or self.motief or self.intentie)


def steer_options() -> dict[str, list[str]]:
    """Beschikbare chip-keuzes voor de UI (accent + energie)."""
    return {"accent": list(_ACCENTS), "energie": list(_ENERGIES)}


def _steer_suffix(steer: CoverSteer | None) -> str:
    """Deterministische stijl-uitbreiding uit de chips (werkt óók in fallback)."""
    if steer is None:
        return ""
    parts: list[str] = []
    if steer.accent and steer.accent in _ACCENTS:
        parts.append(_ACCENTS[steer.accent])
    if steer.energie and steer.energie in _ENERGIES:
        parts.append(_ENERGIES[steer.energie])
    if steer.motief and steer.motief.strip():
        parts.append(f"emphasising the motif of {steer.motief.strip()}")
    if not parts:
        return ""
    return ". " + ". ".join(parts)

_ART_SYSTEM = (
    "Je bent een art-director voor een verfijnde, kosmische community van "
    "AI-makers. Je krijgt een korte profielbrief van één lid. Schrijf in het "
    "ENGELS één korte, concrete VISUELE METAFOOR (beeldende zelfstandige "
    "naamwoorden/een scène, GEEN volzin, GEEN proza) die abstract en symbolisch "
    "uitdrukt WAT DIT LID MAAKT OF DOET. Voorbeelden van de vorm: 'soundwaves "
    "dissolving into a constellation', 'aurora over flowing rivers of data', "
    "'a lattice of light forming neural pathways'. Maximaal ~18 woorden. Noem "
    "GEEN tekst, namen, gezichten, merken of logo's. Antwoord met UITSLUITEND de "
    "metafoor, niets anders."
)


def _client():
    import anthropic

    return anthropic.Anthropic()


def _brief(profile: Profile, *, intentie: str | None = None) -> str:
    """Compacte, gegronde profielbrief voor de art-director (geen PII-naam nodig).

    ``intentie`` = de lid-gekozen intentie-regel; die gaat als extra brief-regel
    mee zodat de art-director 'm interpreteert (nooit als rauwe prompt — het
    stijl-anker blijft leidend).
    """
    parts: list[str] = []
    if intentie and intentie.strip():
        parts.append(f"Intentie van de maker voor dit beeld: {intentie.strip()}")
    if profile.headline:
        parts.append(f"Headline: {profile.headline.strip()}")
    if profile.makes_summary:
        parts.append(f"Maakt: {profile.makes_summary.strip()}")
    if profile.bio:
        parts.append(f"Over: {' '.join(profile.bio.split())[:300]}")
    if profile.offerings:
        first = profile.offerings[0]
        line = (first.title or "").strip()
        if first.description:
            line += f" — {' '.join(first.description.split())[:160]}"
        if line:
            parts.append(f"Project: {line}")
    tags = [t.name for t in profile.tags][:8]
    if tags:
        parts.append("Onderwerpen: " + ", ".join(tags))
    return "\n".join(parts).strip()


def _text_from(msg: object) -> str:
    out: list[str] = []
    for block in getattr(msg, "content", None) or []:
        if getattr(block, "type", None) == "text":
            out.append(getattr(block, "text", "") or "")
    return " ".join("".join(out).split()).strip()


def build_prompt(
    profile: Profile, *, client=None, steer: CoverSteer | None = None
) -> str:
    """Een gegronde, persoonlijke cover-prompt (kosmische stijl + visuele metafoor).

    ``steer`` = optionele lid-sturing (hero-studio): accent/energie/motief worden
    deterministisch ná de metafoor toegevoegd (werkt óók in fallback); de
    intentie-regel gaat als extra brief naar de art-director (alleen bij AI-aan).

    Valt terug op de deterministische ``cover_prompt`` bij AI-uit, lege brief of
    een fout — de cover faalt nooit hierop.
    """
    suffix = _steer_suffix(steer)
    intentie = steer.intentie if steer else None
    fallback = cover_prompt(
        profile.bio or profile.headline, [t.name for t in profile.tags]
    )
    fallback = f"{fallback}{suffix}"
    if not settings.ai_enrich_enabled:
        return fallback
    brief = _brief(profile, intentie=intentie)
    if not brief:
        return fallback
    try:
        client = client or _client()
        msg = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_ART_SYSTEM,
            messages=[{"role": "user", "content": brief}],
        )
    except Exception:  # noqa: BLE001 — best-effort; de cover mag nooit breken
        logger.exception("Cover-art-director faalde voor profiel %s", profile.id)
        return fallback
    metaphor = _text_from(msg)[:200].strip().strip('"').strip()
    if not metaphor:
        return fallback
    # Stijl-anker eerst (garandeert identiteit + geen tekst/gezichten/logo's),
    # dan de gegronde metafoor, dan de lid-sturing.
    return f"{_COVER_STYLE}. Evoking: {metaphor}{suffix}"
