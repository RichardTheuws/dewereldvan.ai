"""oEmbed-showcase (pivot Fase C, increment 1) — video/audio-werk-items uit een link.

Een lid plakt een YouTube/Vimeo/SoundCloud/Spotify-link bij een werk-item; we maken
er een ingesloten **showreel-speler** van. Verbaas-door-intelligentie: geen
upload-formulier, gewoon een link.

VEILIGHEID (twee lagen):
1. **Geen SSRF**: we bevragen alleen de oEmbed-endpoints van een vaste provider-
   allowlist (hosts die wíj kennen), met de lid-URL als query-param. We halen de
   door-het-lid-opgegeven host NOOIT zelf op.
2. **Geen XSS**: we vertrouwen de door de provider teruggegeven HTML niet. We trekken
   alleen de embed-``src`` eruit, valideren dat die https is én van een toegestane
   embed-host, en bouwen de ``<iframe>`` daarna ZELF (sandboxed, lazy, geen autoplay).

Alles is fail-safe: élke fout (geen match, netwerk, parse, ongeldige src) → ``None``,
waarna de UI terugvalt op een gewone link-kaart. Embeds zijn gratis → niet gegated op AI.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.models.base import OfferingKind

logger = logging.getLogger(__name__)

__all__ = ["resolve", "detect_kind"]

_TIMEOUT = 6.0
_SRC_RE = re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE)


@dataclass(frozen=True)
class _Provider:
    hosts: frozenset[str]  # lid-URL-hosts die deze provider matchen
    kind: OfferingKind
    oembed: str  # ons bekende oEmbed-endpoint (allowlist — wat we ophalen)
    embed_hosts: frozenset[str]  # toegestane hosts in de iframe-src
    shape: str = "video"  # "video" (16:9) | "audio" (vaste hoogte)


_PROVIDERS: tuple[_Provider, ...] = (
    _Provider(
        hosts=frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}),
        kind=OfferingKind.video,
        oembed="https://www.youtube.com/oembed",
        embed_hosts=frozenset({"www.youtube.com", "youtube.com", "www.youtube-nocookie.com"}),
    ),
    _Provider(
        hosts=frozenset({"vimeo.com", "www.vimeo.com"}),
        kind=OfferingKind.video,
        oembed="https://vimeo.com/api/oembed.json",
        embed_hosts=frozenset({"player.vimeo.com"}),
    ),
    _Provider(
        hosts=frozenset({"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"}),
        kind=OfferingKind.audio,
        oembed="https://soundcloud.com/oembed",
        embed_hosts=frozenset({"w.soundcloud.com"}),
        shape="audio",
    ),
    _Provider(
        hosts=frozenset({"open.spotify.com", "spotify.com"}),
        kind=OfferingKind.audio,
        oembed="https://open.spotify.com/oembed",
        embed_hosts=frozenset({"open.spotify.com"}),
        shape="audio",
    ),
)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _match(url: str) -> _Provider | None:
    host = _host(url)
    if not host:
        return None
    for p in _PROVIDERS:
        if host in p.hosts:
            return p
    return None


def detect_kind(url: str | None) -> OfferingKind | None:
    """Snelle, netwerkloze soort-detectie uit de host (None = geen embed-provider)."""
    if not url:
        return None
    p = _match(url)
    return p.kind if p else None


def _safe_embed_src(html: str, allowed_hosts: frozenset[str]) -> str | None:
    """Trek de iframe-src uit de provider-HTML en valideer 'm (https + allowlist-host)."""
    m = _SRC_RE.search(html or "")
    if not m:
        return None
    src = m.group(1)
    parsed = urlparse(src)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed_hosts:
        return None
    return src


def _build_iframe(src: str, shape: str) -> str:
    """Bouw ZELF een nette, sandboxed iframe uit de gevalideerde src (geen autoplay)."""
    sandbox = "allow-scripts allow-same-origin allow-presentation allow-popups"
    allow = "fullscreen; picture-in-picture; encrypted-media; clipboard-write"
    if shape == "audio":
        return (
            f'<iframe class="embed-frame embed-frame--audio" src="{src}" '
            f'loading="lazy" sandbox="{sandbox}" allow="{allow}" '
            f'title="Ingesloten audio"></iframe>'
        )
    return (
        '<div class="embed-frame embed-frame--video">'
        f'<iframe src="{src}" loading="lazy" sandbox="{sandbox}" allow="{allow}" '
        f'allowfullscreen title="Ingesloten video"></iframe></div>'
    )


def resolve(url: str | None) -> tuple[OfferingKind, str] | None:
    """Een embed-link → ``(kind, veilige iframe-HTML)``; ``None`` bij geen match/fout.

    Fail-safe: de aanroeper valt bij ``None`` terug op een gewone link-kaart.
    """
    if not url:
        return None
    provider = _match(url)
    if provider is None:
        return None
    try:
        resp = httpx.get(
            provider.oembed,
            params={"url": url, "format": "json", "maxwidth": 960},
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "dewereldvan.ai/1.0 (+oembed)"},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("oEmbed-fetch faalde voor %s (%s) → link-fallback.", provider.oembed, exc)
        return None

    src = _safe_embed_src(data.get("html", ""), provider.embed_hosts)
    if src is None:
        logger.info("oEmbed gaf geen geldige embed-src (%s) → link-fallback.", url)
        return None
    return provider.kind, _build_iframe(src, provider.shape)
