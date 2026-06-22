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
import threading
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Offering, OfferingKind
from app.services import browser_render_service, photo_service

logger = logging.getLogger(__name__)

# In-proces guard: voorkom dat hetzelfde project tegelijk door twee threads wordt
# verrijkt (bv. lazy-on-view onder gelijktijdige hits). Best-effort, per-proces.
_inflight: set[int] = set()
_inflight_lock = threading.Lock()

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


def summarize(url: str, *, markdown: str | None = None, client=None) -> str | None:
    """Gegronde NL-samenvatting van de pagina op ``url`` (of None).

    Haalt de markdown via Cloudflare op (of gebruikt de meegegeven ``markdown`` —
    zodat ``enrich_offering`` de pagina maar één keer hoeft op te halen) en laat
    Claude die samenvatten. Een gewone call, geen server-tools. Gated op
    ``ai_enrich_enabled``.
    """
    if not settings.ai_enrich_enabled or not url:
        return None
    md = markdown if markdown is not None else browser_render_service.markdown(url)
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


# --------------------------------------------------------------------------- #
# Workshop/sessie-detectie (pivot Fase C inc. 2) — datum + locatie uit de link #
# --------------------------------------------------------------------------- #

_EVENT_TOOL = {
    "name": "record_event",
    "description": (
        "Leg vast of deze pagina een workshop, sessie, training, talk of event "
        "aankondigt of documenteert (iets met een datum dat een maker geeft/gaf)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "is_event": {
                "type": "boolean",
                "description": "True alleen bij een duidelijk event met een datum.",
            },
            "date_iso": {
                "type": "string",
                "description": "Datum (evt. tijd) in ISO 8601, bv. 2026-07-15 of 2026-07-15T19:00. Leeg indien onbekend.",
            },
            "location": {
                "type": "string",
                "description": "'Online', een plaats of een venue. Leeg indien onbekend.",
            },
        },
        "required": ["is_event"],
    },
}
_EVENT_SYSTEM = (
    "Bepaal of de gegeven pagina-tekst een workshop, sessie, training, talk of event "
    "aankondigt of documenteert. Gebruik UITSLUITEND wat in de tekst staat — verzin "
    "geen datum of locatie. Roep record_event exact één keer aan."
)


def _tool_input(msg: object, name: str) -> dict | None:
    """Lees de ``input`` van het ``tool_use``-blok met ``name`` uit een antwoord."""
    for block in getattr(msg, "content", None) or []:
        b_type = getattr(block, "type", None)
        b_name = getattr(block, "name", None)
        if b_type == "tool_use" and b_name == name:
            data = getattr(block, "input", None)
            return data if isinstance(data, dict) else None
    return None


def _parse_iso(value: str | None) -> datetime | None:
    """Parse een ISO-datum/tijd → naïeve datetime (of None bij onbekend/ongeldig)."""
    if not value:
        return None
    raw = value.strip().replace("Z", "")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        # Val terug op enkel de datum (eerste 10 tekens: YYYY-MM-DD).
        try:
            return datetime.fromisoformat(raw[:10])
        except ValueError:
            return None


def extract_event(markdown: str | None, *, client=None) -> tuple[datetime | None, str | None] | None:
    """Is dit een workshop/event? → ``(event_at, location)``; anders ``None``.

    Een goedkope, gegronde Haiku-tool-call op de al-opgehaalde pagina-markdown.
    Fail-safe: geen markdown / geen event / élke fout → ``None`` (blijft 'project').
    """
    if not settings.ai_enrich_enabled or not markdown:
        return None
    try:
        client = client or _client()
        msg = client.messages.create(
            model=settings.triage_model,
            max_tokens=200,
            system=_EVENT_SYSTEM,
            tools=[_EVENT_TOOL],
            tool_choice={"type": "tool", "name": "record_event"},
            messages=[{"role": "user", "content": markdown[:_MARKDOWN_CHARS]}],
        )
    except Exception:  # noqa: BLE001 — best-effort; mag verrijking nooit breken
        logger.exception("Event-extractie faalde")
        return None
    data = _tool_input(msg, "record_event")
    if not data or not data.get("is_event"):
        return None
    location = (data.get("location") or "").strip()[:200] or None
    return _parse_iso(data.get("date_iso")), location


def enrich_offering(db: Session, offering: Offering, *, client=None) -> bool:
    """Vul de ONTBREKENDE verrijking (screenshot/samenvatting) voor één offering.

    Returnt True als er iets is gezet. Alleen wat nog mist wordt gegenereerd (een
    URL-wijziging nullt beide → dan herstellen ze allebei). Screenshot en
    samenvatting zijn los best-effort: de één kan slagen terwijl de ander overslaat.
    Caller commit.
    """
    url = (offering.url or "").strip()
    if not url:
        return False

    changed = False

    # --- Screenshot-hero (Cloudflare Browser Rendering) — alleen als die mist ---
    if not offering.screenshot_url:
        png = browser_render_service.screenshot(url)
        if png:
            new_url = photo_service.save_screenshot(png, offering.id)
            if new_url:
                offering.screenshot_url = new_url
                changed = True

    # --- Pagina-tekst één keer ophalen voor samenvatting + workshop-detectie ---
    # De workshop-detectie loopt mee op de EERSTE verrijking (terwijl de samenvatting
    # gemaakt wordt) → geen extra pagina-fetch op latere passes (idempotent).
    md: str | None = None
    need_summary = not offering.summary
    need_event = offering.kind == OfferingKind.project and need_summary
    if settings.ai_enrich_enabled and (need_summary or need_event):
        md = browser_render_service.markdown(url)

    # --- Gegronde samenvatting — alleen als die mist ---
    if need_summary and md:
        summary = summarize(url, markdown=md, client=client)
        if summary:
            offering.summary = summary
            changed = True

    # --- Workshop/sessie-detectie (alleen voor 'project'-items) ---
    # Plakt een trainer een event-/workshop-link, dan herkent de agent dat en haalt
    # datum + locatie eruit → kind=workshop (render = workshop-kaart i.p.v. project).
    if need_event and md:
        ev = extract_event(md, client=client)
        if ev is not None:
            offering.kind = OfferingKind.workshop
            offering.event_at, offering.location = ev
            changed = True

    return changed


def enrich_one(offering_id: int) -> bool:
    """Verrijk één offering in een EIGEN sessie (voor de achtergrond-thread/cron).

    Laadt de offering, vult de ontbrekende verrijking, commit. Returnt True bij
    een update. Best-effort: vangt alles (mag nooit een thread laten crashen)."""
    try:
        with SessionLocal() as db:
            offering = db.get(Offering, offering_id)
            if offering is None:
                return False
            changed = enrich_offering(db, offering)
            if changed:
                db.commit()
            return changed
    except Exception:  # noqa: BLE001 — achtergrond-verrijking mag nooit crashen
        logger.exception("Async-verrijking faalde voor offering %s", offering_id)
        return False


def trigger_async(offering_id: int) -> None:
    """Start de verrijking van één project in de achtergrond (geen UX-vertraging).

    Gebruikt na het toevoegen/wijzigen van een project (direct verrijken) én
    lazy bij de eerste paginaweergave. Poort: geen Cloudflare-creds → no-op (ook
    geen thread-ruis in dev/test). Dubbel-werk-guard via ``_inflight`` zodat
    gelijktijdige triggers voor hetzelfde project niet stapelen.
    """
    if not browser_render_service.configured():
        return
    with _inflight_lock:
        if offering_id in _inflight:
            return
        _inflight.add(offering_id)

    def _run() -> None:
        try:
            enrich_one(offering_id)
        finally:
            with _inflight_lock:
                _inflight.discard(offering_id)

    threading.Thread(target=_run, name=f"enrich-{offering_id}", daemon=True).start()


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
