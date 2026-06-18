"""Publieke ledenpagina (L2) — kosmische constellatie van publieke leden.

Bevat uitsluitend ``/leden`` (overzicht + de htmx-filter-fragmentroute). De
persoonsdetailpagina ``/leden/{slug}`` blijft in ``app/routers/profiles.py``
(daar verrijkt, niet verplaatst).

Eén poort: ``members_service.list_public_profiles`` toont alléén
``visibility=public`` van een goedgekeurde eigenaar (spiegelt ``can_view(anon)``);
besloten/geschorst lekt nooit. Indexeerbaar (geen noindex).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import (
    emphasis_service,
    members_service,
    photo_service,
    seo_service,
)

router = APIRouter(tags=["members"])


def _render(request: Request, name: str, ctx: dict | None = None, **kw) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, name, ctx or {}, **kw)


def _grid_context(profiles) -> dict:
    """Gedeelde context voor zowel de hele pagina als het htmx-grid-fragment.

    Levert de helpers (``emphasis_class``/``photo_or_initials``) als callables
    mee zodat de template geen logica hoeft te bevatten.
    """
    return {
        "profiles": profiles,
        "emphasis_class": emphasis_service.emphasis_class,
        "photo_for": photo_service.photo_or_initials,
    }


@router.get("/leden", response_class=HTMLResponse)
def members_index(
    request: Request,
    tag: str = Query("", alias="tag"),
    maakt: str = Query("", alias="maakt"),
    zoekt: str = Query("", alias="zoekt"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """De kosmische constellatie van publieke leden + server-side filter/zoek.

    htmx-verzoeken (``HX-Request``) krijgen alléén het gefilterde grid-fragment
    terug; een gewone navigatie of deeplink met querystring krijgt de volledige,
    indexeerbare pagina (zodat een gedeelde gefilterde URL ook stand-alone werkt).
    """
    profiles = members_service.list_public_profiles(
        db, tag=tag, maakt=maakt, zoekt=zoekt
    )
    ctx = _grid_context(profiles)
    ctx.update({"tag": tag, "maakt": maakt, "zoekt": zoekt})

    if request.headers.get("HX-Request"):
        return _render(request, "members/_grid.html", ctx)

    ctx["canonical"] = seo_service.canonical_url("/leden")
    return _render(request, "members/index.html", ctx)
