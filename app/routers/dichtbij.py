"""Dichtbij-router — opt-in grof locatie-gebied (PRD-samenkomen fase 2).

Self-only (``require_member``). Een lid geeft optioneel z'n postcode(-begin) op;
wij bewaren ALLEEN het 2-cijferige gebied + middelpunt (nooit het exacte adres) en
gebruiken dat om bij een samenkomst nabije makers voor te stellen. Standaard uit;
één klik wist het weer. CSRF: htmx erft ``X-CSRF-Token`` via de body-``hx-headers``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_member
from app.models import Member
from app.services import location_service

router = APIRouter(tags=["dichtbij"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _panel_ctx(member: Member, *, error: str | None = None, saved: bool = False) -> dict:
    # Het paneel rendert uit ``profile`` (self-sufficient), zodat het zowel als
    # htmx-swap als ingebed in de profiel-settings werkt.
    return {"profile": member.profile, "error": error, "saved": saved}


# NB: "Dichtbij" is géén aparte pagina (het is een profiel-instelling, geen bestemming) —
# het paneel leeft in /profiel/bewerken. Alleen de mutatie-endpoints staan hier.


@router.post("/profiel/dichtbij", response_class=HTMLResponse)
def dichtbij_set(
    request: Request,
    postcode: str = Form(""),
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Zet het grove gebied uit een postcode(-begin). Onherkenbaar → nette hint."""
    profile = member.profile
    if profile is None:
        return _render(
            request, "dichtbij/_panel.html",
            _panel_ctx(member, error="Maak eerst je profiel aan."),
            status_code=400,
        )
    area = location_service.set_area(db, profile, postcode)
    if area is None:
        return _render(
            request, "dichtbij/_panel.html",
            _panel_ctx(member, error="Dat herken ik niet als postcode. Geef bijvoorbeeld 3511 of alleen 35."),
            status_code=400,
        )
    db.commit()
    return _render(request, "dichtbij/_panel.html", _panel_ctx(member, saved=True))


@router.post("/profiel/dichtbij/wis", response_class=HTMLResponse)
def dichtbij_clear(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Wis het locatie-gebied (opt-out)."""
    if member.profile is not None:
        location_service.clear_area(db, member.profile)
        db.commit()
    return _render(request, "dichtbij/_panel.html", _panel_ctx(member))
