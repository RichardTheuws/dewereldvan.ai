"""Gidsen — leerpagina's die tonen hoe je met AI je profiel verrijkt.

GET ``/gids/scene`` — de scene-gids (PRD maker-podium, fase 1): leert leden de
pipeline referentie → beeld personaliseren → motion-transfer → hero-video, met
kopieerbare prompt-patronen. Publiek + volledig statisch (nul AI-kosten, ook
voor anoniem — harde constraint). De concierge verwijst ernaar via de
``scene_gids``-nudge; de hero-studio linkt er direct heen.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.deps import current_member
from app.models import Member
from app.services import seo_service

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
