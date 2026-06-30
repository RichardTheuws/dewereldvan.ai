"""FalImageGenerator — fal.ai (flux/schnell) cover-generatie via httpx.

Roept het fal.ai sync-endpoint aan en parset ``result["images"][0]["url"]``.
De cover is OPTIONEEL: elke fout (netwerk, non-2xx, lege/ongeldige payload)
resulteert in ``GeneratedImage(url=None)`` — nooit een exception die naar de
caller lekt. Geen ``fal-client``-dependency nodig; httpx staat er al.
"""

from __future__ import annotations

import logging

import httpx

from app.ai.base import GeneratedImage

logger = logging.getLogger(__name__)

_FAL_ENDPOINT = "https://fal.run/fal-ai/flux/schnell"
_TIMEOUT_SEC = 60.0
# Bovengrens op het aantal varianten per generatie (kostencap + fal-limiet).
_MAX_VARIANTS = 4


class FalImageGenerator:
    def __init__(self, fal_key: str) -> None:
        self.fal_key = fal_key

    def generate(self, prompt: str) -> GeneratedImage:
        payload: dict[str, object] = {
            "prompt": prompt,
            "image_size": "landscape_16_9",
        }
        try:
            response = httpx.post(
                _FAL_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Key {self.fal_key}"},
                timeout=_TIMEOUT_SEC,
            )
        except httpx.HTTPError as exc:
            logger.warning("fal.ai netwerkfout, cover overgeslagen: %s", exc)
            return GeneratedImage(url=None)

        if response.status_code >= 300:
            logger.warning(
                "fal.ai afgewezen (status %s), cover overgeslagen", response.status_code
            )
            return GeneratedImage(url=None)

        try:
            data = response.json()
            url = data["images"][0]["url"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("fal.ai onverwachte payload, cover overgeslagen: %s", exc)
            return GeneratedImage(url=None)

        if not isinstance(url, str) or not url:
            return GeneratedImage(url=None)
        return GeneratedImage(url=url)

    def generate_many(self, prompt: str, count: int) -> list[GeneratedImage]:
        """Vraag fal.ai om ``count`` varianten (``num_images``) in één call.

        Spiegelt ``generate`` in robuustheid: elke fout (netwerk, non-2xx, lege/
        ongeldige payload) → lege lijst. Levert alleen items met een geldige URL,
        ook als fal er minder teruggeeft dan gevraagd.
        """
        count = max(1, min(int(count), _MAX_VARIANTS))
        payload: dict[str, object] = {
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "num_images": count,
        }
        try:
            response = httpx.post(
                _FAL_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Key {self.fal_key}"},
                timeout=_TIMEOUT_SEC,
            )
        except httpx.HTTPError as exc:
            logger.warning("fal.ai netwerkfout, varianten overgeslagen: %s", exc)
            return []

        if response.status_code >= 300:
            logger.warning(
                "fal.ai afgewezen (status %s), varianten overgeslagen",
                response.status_code,
            )
            return []

        try:
            images = response.json()["images"]
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("fal.ai onverwachte payload, varianten overgeslagen: %s", exc)
            return []

        out: list[GeneratedImage] = []
        for item in images if isinstance(images, list) else []:
            url = item.get("url") if isinstance(item, dict) else None
            if isinstance(url, str) and url:
                out.append(GeneratedImage(url=url))
        return out
