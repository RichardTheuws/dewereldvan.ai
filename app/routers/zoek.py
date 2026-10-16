"""Zoeken over de hele hub (PRD voordeur §3.1) — ``GET /zoek?q=``.

Publiek, nul AI. Zonder ``q`` (of te kort) toont de pagina de snelkeuzes en is ze
indexeerbaar; een resultaatpagina is ``noindex`` (eindeloze combinaties).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_member
from app.models import Member
from app.services import directory_service, search_service, seo_service

router = APIRouter(tags=["zoek"])


@router.get("/zoek", response_class=HTMLResponse)
def zoek(
    request: Request,
    q: str = Query(""),
    member: Member | None = Depends(current_member),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    res = search_service.search(db, q)
    searched = search_service.is_searchable(res.query)
    return request.app.state.templates.TemplateResponse(
        request,
        "zoek/index.html",
        {
            "member": member,
            "q": res.query,
            "res": res,
            "searched": searched,
            "noindex": searched,
            "canonical": seo_service.canonical_url("/zoek"),
            "disciplines_for": lambda p: directory_service.maker_record(p)["disciplines"],
            "guides": directory_service.GUIDES,
        },
    )
