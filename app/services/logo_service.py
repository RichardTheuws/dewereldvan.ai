"""Tool-logo-verrijking — best-effort logo ophalen voor een tool-URL.

Spiegelt het project-enrich-patroon (``project_enrich_service``): vul het
ONTBREKENDE ``tool.logo_url`` los best-effort, met letter-tile fallback (de
template rendert initialen als ``logo_url`` None blijft). Een fout mag NOOIT een
pagina, de save of de job breken.

Twee bronnen, in volgorde:

A) PRIMAIR — directe favicon/og-fetch via httpx (lichtst, geen Cloudflare-kosten):
   parse de ``<head>`` op ``og:image`` en ``<link rel="icon|apple-touch-icon">``,
   resolve relatief→absoluut, val terug op ``/favicon.ico``, download (alleen
   ``image/*``, gecapt op ``max_upload_bytes``) en verwerk via Pillow.
B) SECUNDAIR (alleen als A faalt én Cloudflare beschikbaar is): haal de
   gerenderde pagina-markdown op (JS-heavy sites) en zoek daar een image-URL.

SSRF-GUARD: elke server-side fetch (de eerste page-load, elke kandidaat-download
en elke redirect-hop) wordt vóór de request door ``_safe_url`` geloodst: niet-
http(s) → geweigerd, en elk opgelost IP dat privé/loopback/link-local/reserved/
multicast is → geweigerd. Redirects volgen we NIET automatisch
(``follow_redirects=False``); elke hop wordt handmatig opnieuw gevalideerd. Zo
kan externe content (og:image/icon/CF-markdown) geen interne doelen raken.

Poort: een eenvoudige ``enabled``-flag (favicon-fetch heeft GEEN CF nodig); de
CF-fallback B is apart gegated op ``browser_render_service.configured()``. De
verrijking draait via de nachtelijke job (``refresh_all`` → ``enrich_one`` per
item in een eigen sessie), niet synchroon bij opslaan.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from app.config import settings
from app.db import SessionLocal
from app.models import Tool
from app.services import browser_render_service, photo_service

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0  # lichte fetch; nooit de flow ophouden.
_HTML_CHARS = 200_000  # cap de HTML-head-parse (kosten + ruis).
_MAX_REDIRECTS = 5  # we volgen handmatig; elke hop opnieuw geguard.
_UA = "Mozilla/5.0 (compatible; dewereldvanbot/1.0; +https://dewereldvan.ai)"

# Head-parsers (best-effort regex; we hebben geen volledige HTML-parser nodig).
_OG_IMAGE = re.compile(
    r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
_OG_IMAGE_ALT = re.compile(
    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:image[\"']",
    re.IGNORECASE,
)
_ICON_LINK = re.compile(
    r"<link[^>]+rel=[\"']([^\"']*icon[^\"']*)[\"'][^>]*>",
    re.IGNORECASE,
)
_HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.IGNORECASE)


# --- SSRF-guard -----------------------------------------------------------


def _safe_url(url: str) -> bool:
    """True als ``url`` http(s) is én geen enkel opgelost IP intern/privé is.

    Resolvet de host (``getaddrinfo``) en weigert zodra één van de opgeloste
    adressen privé/loopback/link-local/reserved/multicast is — zo kan een doel
    (of een redirect/og:image/CF-markdown-kandidaat) geen interne dienst raken.
    Faalt de resolve of is er geen host → onveilig (False).
    """
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https"):
        return False
    host = parts.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, parts.port or None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        sockaddr = info[4]
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def _client() -> httpx.Client:
    # follow_redirects=False: we valideren elke hop zelf via ``_guarded_get``.
    return httpx.Client(
        follow_redirects=False,
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA},
    )


def _guarded_get(client: httpx.Client, url: str) -> httpx.Response | None:
    """GET ``url`` met SSRF-guard op élke (redirect-)hop. None bij weigering/fout.

    Volgt redirects handmatig (max ``_MAX_REDIRECTS``); vóór elke request wordt de
    bestemming door ``_safe_url`` geloodst. Een geweigerde of mislukte hop →
    None (best-effort: behandeld als "geen logo").
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        if not _safe_url(current):
            return None
        try:
            resp = client.get(current)
        except httpx.HTTPError:
            return None
        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                return None
            current = urljoin(current, location)
            continue
        return resp
    return None


def _candidate_urls_from_html(html: str, base_url: str) -> list[str]:
    """Trek kandidaat-logo/icon-URLs uit een HTML-head (absoluut gemaakt)."""
    out: list[str] = []
    head = html[:_HTML_CHARS]
    for pat in (_OG_IMAGE, _OG_IMAGE_ALT):
        m = pat.search(head)
        if m:
            out.append(urljoin(base_url, m.group(1).strip()))
    for m in _ICON_LINK.finditer(head):
        href = _HREF.search(m.group(0))
        if href:
            out.append(urljoin(base_url, href.group(1).strip()))
    # Dedup met behoud van volgorde.
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def _download_image(client: httpx.Client, url: str) -> bytes | None:
    """Download ``url`` iff het een ``image/*`` is binnen ``max_upload_bytes``.

    Door de SSRF-guard (``_guarded_get``): externe content kan zo geen interne
    doelen laten downloaden.
    """
    resp = _guarded_get(client, url)
    if resp is None or resp.status_code != 200:
        return None
    ctype = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not ctype.startswith("image/"):
        return None
    content = resp.content
    if not content or len(content) > settings.max_upload_bytes:
        return None
    return content


def fetch_logo_bytes(url: str) -> bytes | None:
    """Best-effort: haal logo-bytes voor ``url`` op (A: favicon/og, B: CF-markdown).

    Retourneert ruwe image-bytes of None. Nooit raisen — alles wordt opgevangen.
    Elke server-side fetch loopt door de SSRF-guard (``_guarded_get``).
    """
    url = (url or "").strip()
    if not url or not _safe_url(url):
        return None
    parts = urlsplit(url)

    try:
        with _client() as client:
            candidates: list[str] = []
            # --- A: directe HTML-head-fetch ---
            resp = _guarded_get(client, url)
            if (
                resp is not None
                and resp.status_code == 200
                and "html" in resp.headers.get("content-type", "").lower()
            ):
                candidates = _candidate_urls_from_html(resp.text, str(resp.url))
            # Fallback binnen A: /favicon.ico op de host.
            candidates.append(f"{parts.scheme}://{parts.netloc}/favicon.ico")

            for cand in candidates:
                data = _download_image(client, cand)
                if data:
                    return data

            # --- B: Cloudflare-markdown (JS-heavy sites) ---
            if browser_render_service.configured():
                md = browser_render_service.markdown(url)
                if md:
                    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", md):
                        cand = urljoin(url, m.group(1).strip())
                        data = _download_image(client, cand)
                        if data:
                            return data
    except Exception:  # noqa: BLE001 — best-effort; logo mag nooit breken
        logger.warning("Logo-fetch faalde voor %s", url, exc_info=True)
        return None
    return None


def enrich_tool(db, tool: Tool) -> bool:
    """Vul het ONTBREKENDE ``tool.logo_url`` best-effort. Returnt True bij update.

    Alleen als er een URL is én er nog geen logo staat. Caller commit.
    """
    if tool.logo_url:
        return False
    url = (tool.url or "").strip()
    if not url:
        return False
    raw = fetch_logo_bytes(url)
    if not raw:
        return False
    new_url = photo_service.save_logo(raw, tool.id)
    if not new_url:
        return False
    tool.logo_url = new_url
    return True


def enrich_one(tool_id: int) -> bool:
    """Verrijk één tool in een EIGEN sessie (achtergrond-thread/cron). Nooit crashen."""
    try:
        with SessionLocal() as db:
            tool = db.get(Tool, tool_id)
            if tool is None:
                return False
            changed = enrich_tool(db, tool)
            if changed:
                db.commit()
            return changed
    except Exception:  # noqa: BLE001 — achtergrond-verrijking mag nooit crashen
        logger.exception("Async-logoverrijking faalde voor tool %s", tool_id)
        return False


def refresh_all(db) -> int:
    """Verrijk elke tool met een URL maar zonder logo. Idempotent. Caller commit.

    Selecteert eerst de te verrijken tool-ids, en verrijkt elk in een EIGEN sessie
    (``enrich_one``, zoals ``project_enrich_service`` per item) zodat één fout de
    batch niet breekt en een mislukte tool de gedeelde sessie niet vervuilt.
    """
    from sqlalchemy import or_, select

    tool_ids = list(
        db.scalars(
            select(Tool.id).where(
                Tool.url.is_not(None),
                Tool.url != "",
                or_(Tool.logo_url.is_(None), Tool.logo_url == ""),
            )
        ).all()
    )
    enriched = 0
    for tool_id in tool_ids:
        try:
            if enrich_one(tool_id):
                enriched += 1
        except Exception:  # noqa: BLE001 — één tool mag de batch niet breken
            logger.exception("Logoverrijking faalde voor tool %s", tool_id)
    return enriched
