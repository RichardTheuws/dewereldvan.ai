"""Project-verrijking — screenshot-hero + gegronde AI-samenvatting per offering.

Voor ``/projecten/{slug}``: vul ``offering.screenshot_url`` (Cloudflare Browser
Rendering) en ``offering.summary`` (korte, gegronde NL-samenvatting uit de
pagina-markdown). Periodiek via ``app.jobs.enrich_projects`` (zelfde patroon als
matches/geheugen: niet synchroon bij opslaan → geen bewerk-vertraging).

GROUNDING: de samenvatting komt UIT de echte pagina-inhoud (CF ``/markdown``) →
een gewone Claude-call (geen server-tools, geen pause_turn-valkuil). Verzint het
model iets niet uit de markdown, dan hoort dat er niet te staan (system-prompt).
Best-effort + gegated op ``ai_enrich_enabled`` (samenvatting) resp. CF-creds
(screenshot): een fout mag NOOIT een pagina of de job breken.
"""

from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Offering
from app.services import browser_render_service, photo_service

logger = logging.getLogger(__name__)

_MODEL = settings.anthropic_model
_MAX_TOKENS = 500
_MARKDOWN_CHARS = 8000  # cap de input naar het model (kosten + ruis).
MAX_SUMMARY_CHARS = 1200

_SUMMARY_SYSTEM = (
    "Je schrijft een korte, zakelijke samenvatting van één project voor een "
    "Nederlandstalige ledengids van AI-makers. Je krijgt de tekst (markdown) van "
    "de projectpagina. Vat in 2 tot 4 zinnen samen WAT het project is en wat het "
    "doet/oplevert. Schrijf in het Nederlands, helder en direct, geen "
    "marketing-superlatieven. Gebruik UITSLUITEND wat in de tekst staat — verzin "
    "geen feiten, cijfers of claims. Staat er te weinig bruikbare inhoud, vat dan "
    "alleen samen wat er wél staat. Antwoord met enkel de samenvatting."
)


def _client():
    import anthropic

    return anthropic.Anthropic()


def _text_from(msg: object) -> str:
    parts: list[str] = []
    for block in getattr(msg, "content", None) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


def summarize(url: str, *, client=None) -> str | None:
    """Gegronde NL-samenvatting van de pagina op ``url`` (of None).

    Haalt de markdown via Cloudflare op en laat Claude die samenvatten — een
    gewone call, geen server-tools. Gated op ``ai_enrich_enabled``.
    """
    if not settings.ai_enrich_enabled or not url:
        return None
    md = browser_render_service.markdown(url)
    if not md:
        return None
    try:
        client = client or _client()
        msg = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SUMMARY_SYSTEM,
            messages=[{"role": "user", "content": md[:_MARKDOWN_CHARS]}],
        )
    except Exception:  # noqa: BLE001 — best-effort; verrijking mag nooit breken
        logger.exception("Project-samenvatting faalde voor %s", url)
        return None
    text = _text_from(msg)[:MAX_SUMMARY_CHARS].strip()
    return text or None


def enrich_offering(db: Session, offering: Offering, *, client=None) -> bool:
    """Vul screenshot + samenvatting voor één offering met een URL. Caller commit.

    Returnt True als er iets is gezet. Screenshot en samenvatting zijn los
    best-effort: de één kan slagen terwijl de ander overslaat.
    """
    url = (offering.url or "").strip()
    if not url:
        return False

    changed = False

    # --- Screenshot-hero (Cloudflare Browser Rendering) ---
    png = browser_render_service.screenshot(url)
    if png:
        new_url = photo_service.save_screenshot(png, offering.id)
        if new_url:
            old = offering.screenshot_url
            offering.screenshot_url = new_url
            if old and old != new_url:
                photo_service.delete_photo(old)  # geen wees-bestand
            changed = True

    # --- Gegronde samenvatting ---
    summary = summarize(url, client=client)
    if summary:
        offering.summary = summary
        changed = True

    return changed


def refresh_all(db: Session, *, client=None) -> int:
    """Verrijk elke offering met een URL maar zonder screenshot óf samenvatting.

    Idempotent: al-verrijkte projecten (beide gezet) worden overgeslagen. Caller
    commit. Bij een URL-wijziging nullt de inline-edit beide velden → her-verrijking.
    """
    offerings = db.scalars(
        select(Offering).where(
            Offering.url.is_not(None),
            Offering.url != "",
            or_(Offering.screenshot_url.is_(None), Offering.summary.is_(None)),
        )
    ).all()
    enriched = 0
    for offering in offerings:
        try:
            if enrich_offering(db, offering, client=client):
                enriched += 1
        except Exception:  # noqa: BLE001 — één project mag de batch niet breken
            logger.exception("Verrijking faalde voor offering %s", offering.id)
    return enriched
