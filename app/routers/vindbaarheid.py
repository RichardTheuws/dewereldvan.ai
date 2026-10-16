"""Je vindbaarheid (PRD hub §4.4) — laat een lid zien dat de vermelding werkt.

GET ``/profiel/vindbaarheid`` (besloten): weergaven door mensen en AI-assistenten,
MCP-zoekresultaten en aanvragen in de laatste 30 dagen, in welke gidsen je staat,
wat een AI-assistent precies over je leest (``directory_service.maker_record``) en
wat er ontbreekt om goed gevonden te worden. Nul AI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_member
from app.models import Member
from app.services import directory_service, profile_service, stats_service
from app.services import visibility as visibility_service

router = APIRouter(tags=["vindbaarheid"])


def _gaps(profile, record: dict, is_public: bool) -> list[tuple[str, str, str]]:
    """(wat ontbreekt, waarom het telt, link) — in volgorde van impact."""
    gaps: list[tuple[str, str, str]] = []
    if not is_public:
        gaps.append((
            "Je profiel is besloten",
            "Bezoekers, zoekmachines en AI-assistenten zien je nu niet, "
            "en niemand kan je een vraag stellen.",
            "/profiel/bewerken#zichtbaarheid",
        ))
    if not profile.headline:
        gaps.append((
            "Geen kopregel",
            "Dit is de zin die een AI-assistent over je citeert. Zeg in één regel wat je doet.",
            "/profiel/ai/bouwen",
        ))
    if not record.get("disciplines"):
        gaps.append((
            "Nog geen zichtbaar werk",
            "Zonder werk op je profiel kom je in geen enkele gids terecht.",
            "/profiel/ai/bouwen",
        ))
    if not record.get("open_voor"):
        gaps.append((
            "Niet aangegeven waar je voor open staat",
            "Wie een trainer of bouwer zoekt, filtert hierop. "
            "Kies bijvoorbeeld klantwerk of trainingen.",
            "/profiel/bewerken",
        ))
    if not record.get("tags"):
        gaps.append((
            "Geen onderwerpen",
            "Tags bepalen bij welke zoekvraag je naar boven komt.",
            "/profiel/bewerken",
        ))
    return gaps


@router.get("/profiel/vindbaarheid", response_class=HTMLResponse)
def vindbaarheid(
    request: Request,
    member: Member = Depends(require_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    profile = profile_service.get_or_create_profile(db, member)
    db.commit()
    is_public = visibility_service.can_view(profile, None)
    record = directory_service.maker_record(profile)
    guides = [
        g for g in directory_service.GUIDES
        if is_public and profile in directory_service.makers_for_guide(db, g)
    ]
    stats = stats_service.summary(db, profile.id, member.id)
    return request.app.state.templates.TemplateResponse(
        request,
        "vindbaarheid/index.html",
        {
            "profile": profile,
            "is_public": is_public,
            "record": record,
            "guides": guides,
            "stats": stats,
            "gaps": _gaps(profile, record, is_public),
        },
    )
