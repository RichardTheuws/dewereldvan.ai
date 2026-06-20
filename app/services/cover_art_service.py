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

from app.ai import _COVER_STYLE, cover_prompt
from app.config import settings
from app.models import Profile

logger = logging.getLogger(__name__)

_MODEL = settings.anthropic_model
_MAX_TOKENS = 120

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


def _brief(profile: Profile) -> str:
    """Compacte, gegronde profielbrief voor de art-director (geen PII-naam nodig)."""
    parts: list[str] = []
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


def build_prompt(profile: Profile, *, client=None) -> str:
    """Een gegronde, persoonlijke cover-prompt (kosmische stijl + visuele metafoor).

    Valt terug op de deterministische ``cover_prompt`` bij AI-uit, lege brief of
    een fout — de cover faalt nooit hierop.
    """
    fallback = cover_prompt(profile.bio or profile.headline, [t.name for t in profile.tags])
    if not settings.ai_enrich_enabled:
        return fallback
    brief = _brief(profile)
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
    # dan de gegronde metafoor.
    return f"{_COVER_STYLE}. Evoking: {metaphor}"
