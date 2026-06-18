"""AI package — ImageGenerator interface + backend selection by settings.

De backend is env-driven (net als EMAIL_BACKEND): ``AI_IMAGE_BACKEND`` kiest
fal vs noop, maar zonder ``FAL_KEY`` valt het altijd terug op de noop-backend
zodat het profiel ook zonder cover werkt.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.ai.base import (
    GeneratedImage,
    ImageGenerateError,
    ImageGenerator,
)
from app.ai.fal_generator import FalImageGenerator
from app.ai.noop_generator import NoopImageGenerator
from app.config import settings

__all__ = [
    "GeneratedImage",
    "ImageGenerateError",
    "ImageGenerator",
    "FalImageGenerator",
    "NoopImageGenerator",
    "get_image_generator",
    "cover_prompt",
]


def get_image_generator() -> ImageGenerator:
    """Return the configured ImageGenerator backend (fallback: Noop)."""
    if settings.ai_image_backend == "fal" and settings.fal_key:
        return FalImageGenerator(settings.fal_key)
    return NoopImageGenerator()


# Stijl-anker zodat covers de "kosmische diepte"-identiteit aanhouden (zie F3:
# diep indigo->zwart, gloed/nebula, GEEN generieke AI-look) i.p.v. willekeurige
# beelden. De cover is een sfeerbeeld, geen letterlijke illustratie van de bio.
_COVER_STYLE: str = (
    "abstract cosmic nebula in deep indigo fading to black, soft violet and cyan "
    "glow, subtle starfield, elegant and editorial, no text, no faces, no logos, "
    "wide cinematic banner"
)
_MAX_TAGS_IN_PROMPT: int = 6
_MAX_BIO_CHARS: int = 240


def cover_prompt(bio: str | None, tags: Iterable[str] | None) -> str:
    """Leid een fal.ai-prompt af uit profiel-essentie (bio + tags).

    Houdt de prompt kort en gegrond: een korte bio-samenvatting + een paar tags
    als thematische hints, ingebed in een vast kosmisch stijl-anker. Faalt nooit
    op lege input — dan levert het puur de stijl-prompt (nebula-fallback).
    """
    parts: list[str] = []

    if bio:
        snippet = " ".join(bio.split())[:_MAX_BIO_CHARS].strip()
        if snippet:
            parts.append(f"evoking the themes of: {snippet}")

    if tags:
        clean = [t.strip() for t in tags if t and t.strip()][:_MAX_TAGS_IN_PROMPT]
        if clean:
            parts.append("motifs: " + ", ".join(clean))

    theme = ". ".join(parts)
    if theme:
        return f"{_COVER_STYLE}. {theme}"
    return _COVER_STYLE
