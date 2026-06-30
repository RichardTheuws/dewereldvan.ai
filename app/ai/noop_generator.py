"""NoopImageGenerator — fallback wanneer FAL_KEY leeg is of backend=noop.

Levert altijd ``GeneratedImage(url=None)``: het profiel toont dan de pure-nebula
fallback-hero in plaats van een cover. Geen netwerk, geen kosten.
"""

from __future__ import annotations

from app.ai.base import GeneratedImage


class NoopImageGenerator:
    def generate(self, prompt: str) -> GeneratedImage:  # noqa: ARG002 - interface
        return GeneratedImage(url=None)

    def generate_many(
        self, prompt: str, count: int
    ) -> list[GeneratedImage]:  # noqa: ARG002 - interface
        # Geen FAL_KEY/backend → geen beelden. Lege lijst zodat de hero-studio
        # de "covers staan uit"-staat toont i.p.v. lege kaders.
        return []
