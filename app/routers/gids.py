"""Gidsen — leerpagina's die tonen hoe je met AI je profiel verrijkt.

GET ``/gids`` + ``/gids/<discipline>`` — overzichtspagina's van de openbare makers
per discipline (PRD hub §4.3): statische intro + de makers + ``CollectionPage``-
JSON-LD. Nul AI. Een pagina zonder openbare makers is ``noindex`` (dunne pagina's
schaden) en nodigt uit om zelf openbaar te worden.

GET ``/gids/scene`` — de scene-gids (PRD maker-podium, fase 1): leert leden de
pipeline referentie → beeld personaliseren → motion-transfer → hero-video, met
kopieerbare prompt-patronen. Publiek + volledig statisch (nul AI-kosten, ook
voor anoniem — harde constraint). De concierge verwijst ernaar via de
``scene_gids``-nudge; de hero-studio linkt er direct heen.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_member
from app.models import Member
from app.services import (
    directory_service,
    emphasis_service,
    members_service,
    openness_service,
    photo_service,
    seo_service,
)
from app.services import visibility as visibility_service

router = APIRouter(tags=["gids"])


@router.get("/gids/scene", response_class=HTMLResponse)
def scene_gids(
    request: Request,
    member: Member | None = Depends(current_member),
) -> HTMLResponse:
    """De scene-gids: statisch, publiek, kosmisch."""
    return request.app.state.templates.TemplateResponse(
        request,
        "gids/scene.html",
        {
            "member": member,
            "canonical": seo_service.canonical_url("/gids/scene"),
        },
    )


@router.get("/gids", response_class=HTMLResponse)
def gids_index(
    request: Request,
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Alle overzichtspagina's met het aantal openbare makers per discipline."""
    makers = directory_service.public_makers(db)
    counts = {slug: n for slug, _label, n in directory_service.discipline_counts(makers)}
    return request.app.state.templates.TemplateResponse(
        request,
        "gids/index.html",
        {
            "member": member,
            "guides": [(g, counts.get(g.discipline, 0)) for g in directory_service.GUIDES],
            "total": len(makers),
            "canonical": seo_service.canonical_url("/gids"),
        },
    )


@router.get("/gids/{path}", response_class=HTMLResponse)
def gids_discipline(
    request: Request,
    path: str,
    open_to: str = Query("", alias="open_voor"),
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    guide = directory_service.guide_by_path(path)
    if guide is None:
        return request.app.state.templates.TemplateResponse(request, "404.html", status_code=404)
    open_to = open_to if openness_service.is_valid(open_to) else ""
    everyone = directory_service.makers_for_guide(db, guide)
    profiles = (
        directory_service.makers_for_guide(db, guide, open_to=open_to) if open_to else everyone
    )
    filtered = bool(open_to)
    return request.app.state.templates.TemplateResponse(
        request,
        "gids/discipline.html",
        {
            "member": member,
            "guide": guide,
            "profiles": profiles,
            "open_to": open_to,
            "openness_options": openness_service.options(),
            # Een gefilterde of lege lijst is geen eigen indexeerbare pagina.
            "noindex": filtered or not everyone,
            "canonical": seo_service.canonical_url(f"/gids/{guide.path}"),
            "jsonld": None
            if (filtered or not everyone)
            else directory_service.jsonld_guide(guide, everyone),
            "others": [g for g in directory_service.GUIDES if g.path != guide.path],
            # De gedeelde kaart (members/_member_star.html) als bezoeker.
            "emphasis_class": emphasis_service.emphasis_class,
            "photo_for": photo_service.photo_or_initials,
            "disciplines_for": members_service.derive_disciplines,
            "section_visible": lambda p, s: visibility_service.public_section_visible(p, s, None),
        },
    )
