"""Cloudflare Browser Rendering — screenshot + markdown van een externe URL.

Voor de project-detailpagina's (``/projecten/{slug}``): een screenshot-hero +
een gegronde samenvatting uit de échte pagina-inhoud. Beide via Cloudflare
Browser Rendering (REST), zodat:
- wij geen headless Chromium of een tweede vendor hoeven te draaien (lage op-last);
- Cloudflare de externe pagina ophaalt (geen SSRF vanuit onze app);
- we de web_fetch/pause_turn-valkuil van de Anthropic-server-tools omzeilen
  (zie [[dewereldvan-ai-engine-constraints]]) — de samenvatting draait op platte
  markdown via een gewone Claude-call (geen server-tools).

Auth = ``settings.cloudflare_api_token`` (Bearer) op
``…/accounts/{account_id}/browser-rendering/{screenshot|markdown}``. De token
heeft de **Browser Rendering**-permissie nodig (dashboard). Geen creds → no-op
(None) zodat dev/test zonder Cloudflare gewoon doordraait. Alles best-effort:
een render-fout mag NOOIT een pagina of de job breken.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_API = "https://api.cloudflare.com/client/v4"
_TIMEOUT = 45.0  # Browser Rendering kan een paar seconden duren.
# Hero-viewport: landschap, geen full-page (we willen de "above the fold"-indruk).
_VIEWPORT = {"width": 1280, "height": 800}


def _configured() -> bool:
    return bool(settings.cloudflare_account_id and settings.cloudflare_api_token)


def _endpoint(kind: str) -> str:
    return f"{_API}/accounts/{settings.cloudflare_account_id}/browser-rendering/{kind}"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.cloudflare_api_token}"}


def screenshot(url: str) -> bytes | None:
    """Maak een viewport-screenshot (PNG-bytes) van ``url``, of None bij fout.

    Cloudflare geeft de afbeelding als binaire body terug op succes; bij een
    fout een JSON-payload. We accepteren alleen een ``image/*``-respons.
    """
    if not _configured() or not url:
        return None
    payload = {
        "url": url,
        "viewport": _VIEWPORT,
        "screenshotOptions": {"type": "png"},
        # 'load' i.p.v. 'networkidle0': veel moderne sites (analytics/polling)
        # bereiken nooit "geen netwerk" → Cloudflare geeft dan 422. 'load' wacht
        # op de pagina + resources — robuust genoeg voor een hero-screenshot.
        "gotoOptions": {"waitUntil": "load", "timeout": 30000},
    }
    try:
        resp = httpx.post(
            _endpoint("screenshot"),
            headers=_headers(),
            json=payload,
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        logger.warning("Browser Rendering screenshot faalde voor %s", url, exc_info=True)
        return None
    if resp.status_code != 200 or not resp.headers.get(
        "content-type", ""
    ).startswith("image/"):
        logger.warning(
            "Browser Rendering screenshot %s → status %s (%s)",
            url,
            resp.status_code,
            resp.headers.get("content-type", "?"),
        )
        return None
    return resp.content


def markdown(url: str) -> str | None:
    """Haal de gerenderde pagina als markdown op (voor de samenvatting), of None.

    Cloudflare's ``/markdown`` levert ``{"success": true, "result": "<md>"}``.
    """
    if not _configured() or not url:
        return None
    try:
        resp = httpx.post(
            _endpoint("markdown"),
            headers=_headers(),
            json={"url": url},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        logger.warning("Browser Rendering markdown faalde voor %s", url, exc_info=True)
        return None
    if resp.status_code != 200:
        logger.warning("Browser Rendering markdown %s → status %s", url, resp.status_code)
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    result = data.get("result") if isinstance(data, dict) else None
    return result.strip() if isinstance(result, str) and result.strip() else None
