"""Cloudflare Turnstile — server-side mens-bewijs vóór elke betaalde call.

De widget levert client-side een token; wij valideren dat **server-side** bij
Cloudflare (``/turnstile/v0/siteverify``) vóór de Opus-call. Geen geldig token →
geen call. Dit alleen al stopt het leeuwendeel van geautomatiseerd misbruik
(doc §2.3).

Veilige default (doc §4.2): zonder ``turnstile_secret_key`` is het hele
niet-lid-AI-pad UIT — ``configured()`` is dan False en de gate weigert met een
nette reden zónder een call te doen (geen sleutels = geen onbedoelde spend).
Gegate net als Telegram zonder token. Faalt stil → False (faal-veilig).
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT = 5.0


def configured() -> bool:
    """True als er een secret-key is (anders is het niet-lid-AI-pad uit)."""
    return bool(settings.turnstile_secret_key)


def verify(token: str | None, remote_ip: str | None = None) -> bool:
    """Valideer een Turnstile-token server-side; False bij elke twijfel.

    Faal-veilig: zonder geconfigureerde key, zonder token, of bij een netwerk-/
    parse-fout → False (geen call). Alleen een expliciet ``success: true`` van
    Cloudflare geeft True.
    """
    if not configured() or not token:
        return False
    payload: dict[str, str] = {
        "secret": settings.turnstile_secret_key or "",
        "response": token,
    }
    if remote_ip and remote_ip != "unknown":
        payload["remoteip"] = remote_ip
    try:
        resp = httpx.post(_VERIFY_URL, data=payload, timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Turnstile siteverify gaf %s", resp.status_code)
            return False
        return resp.json().get("success") is True
    except (httpx.HTTPError, ValueError):
        logger.warning("Turnstile siteverify faalde", exc_info=True)
        return False
