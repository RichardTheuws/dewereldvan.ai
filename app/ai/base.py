"""ImageGenerator interface for AI-native cover generation (F2).

Spiegelt het ``EmailSender``-patroon (``app/email/base.py``): een ``Protocol`` +
backends + factory-via-settings. De cover is OPTIONEEL — een profiel werkt
zonder. Daarom faalt generatie gracieus: bij elke fout levert een backend
``GeneratedImage(url=None)`` in plaats van te raisen. ``ImageGenerateError``
bestaat voor backends die expliciet willen signaleren, maar de factory-callers
behandelen ``url=None`` als "geen cover".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeneratedImage:
    """Resultaat van een cover-generatie. ``url=None`` => geen cover beschikbaar."""

    url: str | None = None


class ImageGenerateError(RuntimeError):
    """Optionele signalering van een backend; cover-callers tolereren url=None."""


class ImageGenerator(Protocol):
    def generate(self, prompt: str) -> GeneratedImage:
        """Genereer een cover-beeld uit ``prompt``. Faalt gracieus (url=None)."""
        ...

    def generate_many(self, prompt: str, count: int) -> list[GeneratedImage]:
        """Genereer tot ``count`` varianten uit ``prompt`` (hero-studio).

        Faalt gracieus: bij elke fout een LEGE lijst (geen exception naar de
        caller). Levert alleen items met een geldige ``url`` — een backend zonder
        beeld (Noop / FAL uit) geeft dus ``[]``.
        """
        ...
