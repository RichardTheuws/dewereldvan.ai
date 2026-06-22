"""Post-draft-service — een agenda-event of nieuwsitem uit ÉÉN vrije input.

De stijl van het platform: geen ingewikkeld formulier. Je geeft één ding — een
**link**, wat **tekst**, of (client-side) **voice** → de agent maakt de draft; jij
controleert en plaatst. Eén goedkope Haiku-tool-call, **gegrond**: zit er een URL in,
dan halen we eerst de echte pagina-inhoud op (Cloudflare markdown) en classificeren we
UITSLUITEND wat daarin staat — nooit een verzonnen datum/locatie. Fail-safe: AI uit of
een fout → een minimale draft (URL ingevuld, titel = eerste regel) zodat het altijd werkt.

De teruggegeven dict gebruikt exact de form-veldnamen, zodat de bestaande
``_form.html`` als "concept — controleer & plaats"-stap pre-fill't (geen nieuw
persist-pad; ``create_event``/``create_news`` + validatie blijven ongemoeid).
"""

from __future__ import annotations

import logging
import re

from app.config import settings
from app.models import EventFrequency, NewsRole
from app.services import browser_render_service

logger = logging.getLogger(__name__)

__all__ = ["draft_event", "draft_news"]

_URL_RE = re.compile(r"https?://[^\s)>\"']+")
_MD_CHARS = 6000  # cap op de opgehaalde pagina-inhoud naar het model
_MAX_TOKENS = 400

_FREQ = {f.value for f in EventFrequency}
_ROLE = {r.value for r in NewsRole}


def _client():
    import anthropic

    return anthropic.Anthropic()


def _extract_url(raw: str) -> str | None:
    m = _URL_RE.search(raw or "")
    return m.group(0).rstrip(".,);") if m else None


def _first_line(raw: str) -> str:
    """Fail-safe titel (AI uit): de eerste betekenisvolle regel, met de URL eruit
    gestript zodat de titel geen kale link bevat."""
    for line in (raw or "").splitlines():
        s = _URL_RE.sub("", line).strip(" -—·,")
        if s:
            return s[:200]
    return ""


def _tool_input(msg: object, name: str) -> dict:
    for block in getattr(msg, "content", None) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == name:
            data = getattr(block, "input", None)
            return data if isinstance(data, dict) else {}
    return {}


def _grounded_content(raw: str, url: str | None) -> str:
    """De input-tekst + (als er een URL is) de echte pagina-inhoud eronder."""
    content = (raw or "").strip()
    if url and settings.ai_enrich_enabled:
        md = browser_render_service.markdown(url)
        if md:
            content = f"{content}\n\n[inhoud van {url}]\n{md[:_MD_CHARS]}"
    return content


def _ai_draft(content: str, tool: dict, system: str, *, client=None) -> dict:
    """Eén forced Haiku-tool-call → de geëxtraheerde velden (of {} bij uit/fout)."""
    if not settings.ai_enrich_enabled or not content.strip():
        return {}
    try:
        client = client or _client()
        msg = client.messages.create(
            model=settings.triage_model,
            max_tokens=_MAX_TOKENS,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": content}],
        )
    except Exception:  # noqa: BLE001 — best-effort; mag de bijdrage nooit breken
        logger.exception("Post-draft AI-call faalde")
        return {}
    return _tool_input(msg, tool["name"])


def _clean(value, cap: int = 4000) -> str:
    return str(value or "").strip()[:cap]


# --------------------------------------------------------------------------- #
# Agenda-event                                                                 #
# --------------------------------------------------------------------------- #

_EVENT_TOOL = {
    "name": "record_event_draft",
    "description": "Leg de gegevens van een AI-event/meetup vast uit de gegeven inhoud.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Naam van de meetup/het event."},
            "frequency": {
                "type": "string",
                "enum": sorted(_FREQ),
                "description": "Cadans: eenmalig, wekelijks, tweewekelijks, maandelijks of doorlopend.",
            },
            "date_iso": {"type": "string", "description": "Eerstvolgende datum (+tijd) in ISO 8601, óf leeg. Verzin NOOIT een datum."},
            "location": {"type": "string", "description": "Plaats / 'Online' / venue, óf leeg."},
            "cadence_note": {"type": "string", "description": "Cadans in mensentaal (bv. 'elke woensdag 18:00'), óf leeg."},
            "description": {"type": "string", "description": "1-2 zinnen waar het over gaat."},
        },
        "required": ["title"],
    },
}
_EVENT_SYSTEM = (
    "Je maakt een agenda-concept voor een Nederlandstalige AI-community. Haal de "
    "event-gegevens UITSLUITEND uit de gegeven inhoud — verzin niets, zeker geen "
    "datum of locatie. Wat je niet zeker weet laat je leeg. Roep record_event_draft "
    "exact één keer aan."
)


def _to_datetime_local(date_iso) -> str:
    """ISO → ``YYYY-MM-DDTHH:MM`` voor het datetime-local-veld. Alleen als er een
    tijd in zit (anders leeg — we verzinnen geen tijd)."""
    s = str(date_iso or "").strip().replace("Z", "")
    if "T" in s and len(s) >= 16:
        return s[:16]
    return ""


def draft_event(raw: str, *, client=None) -> dict:
    """Bouw een event-concept uit vrije input (link/tekst). Form-veldnamen."""
    url = _extract_url(raw)
    fields = _ai_draft(_grounded_content(raw, url), _EVENT_TOOL, _EVENT_SYSTEM, client=client)
    freq = str(fields.get("frequency") or "").strip()
    return {
        "title": _clean(fields.get("title"), 200) or _first_line(raw),
        "frequency": freq if freq in _FREQ else "eenmalig",
        "next_at": _to_datetime_local(fields.get("date_iso")),
        "location": _clean(fields.get("location"), 160),
        "cadence_note": _clean(fields.get("cadence_note"), 120),
        "url": url or "",
        "description": _clean(fields.get("description")),
    }


# --------------------------------------------------------------------------- #
# Nieuws                                                                       #
# --------------------------------------------------------------------------- #

_NEWS_TOOL = {
    "name": "record_news_draft",
    "description": "Leg de gegevens van een nieuwsartikel/publicatie vast uit de inhoud.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Kop van het artikel."},
            "source": {"type": "string", "description": "Publicatie/bron (bv. NRC, Emerce, eigen blog), óf leeg."},
            "role": {
                "type": "string",
                "enum": sorted(_ROLE),
                "description": "Rol van de inzender: geschreven (zelf), geinterviewd, vermeld (uitgelicht), of gedeeld.",
            },
            "date_iso": {"type": "string", "description": "Publicatiedatum (YYYY-MM-DD), óf leeg. Verzin NOOIT een datum."},
            "description": {"type": "string", "description": "1-2 zinnen waar het over gaat."},
        },
        "required": ["title"],
    },
}
_NEWS_SYSTEM = (
    "Je maakt een nieuws-concept voor een Nederlandstalige AI-community. Haal de "
    "gegevens UITSLUITEND uit de gegeven inhoud — verzin geen bron of datum. Wat je "
    "niet zeker weet laat je leeg. Roep record_news_draft exact één keer aan."
)


def draft_news(raw: str, *, client=None) -> dict:
    """Bouw een nieuws-concept uit vrije input (link/tekst). Form-veldnamen."""
    url = _extract_url(raw)
    fields = _ai_draft(_grounded_content(raw, url), _NEWS_TOOL, _NEWS_SYSTEM, client=client)
    role = str(fields.get("role") or "").strip()
    date = str(fields.get("date_iso") or "").strip()[:10]
    return {
        "title": _clean(fields.get("title"), 200) or _first_line(raw),
        "url": url or "",
        "role": role if role in _ROLE else "gedeeld",
        "source": _clean(fields.get("source"), 160),
        "published_at": date if len(date) == 10 else "",
        "description": _clean(fields.get("description")),
    }
