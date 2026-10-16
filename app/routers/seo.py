"""SEO-laag (L4) — sitemap + robots voor de publieke buitenkant.

- ``GET /sitemap.xml``  alle PUBLIEKE personen + projecten (besloten/geschorst
  uitgesloten via ``seo_service.sitemap_entries`` — dezelfde poort als
  ``can_view(anon)``).
- ``GET /makers.json`` de openbare gids als data (PRD hub §4.2), via
  ``directory_service`` — dezelfde poort als het profiel voor een bezoeker.
- ``GET /llms.txt``    korte wegwijzer voor AI-assistenten (llmstxt.org-vorm).
- ``GET /robots.txt``   ``Sitemap:``-verwijzing + ``Disallow`` van de besloten/
  ingelogde paden.

Beide server-rendered; geen DB-write. De ``base_url`` voor absolute loc's komt
uit ``seo_service`` (settings.base_url).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.services import directory_service, seo_service

router = APIRouter(tags=["seo"])


@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request) -> HTMLResponse:
    """Publieke, indexeerbare privacyverklaring (AVG/ePrivacy). Statisch, geen DB."""
    return request.app.state.templates.TemplateResponse(
        request,
        "privacy.html",
        {"canonical": seo_service.canonical_url("/privacy")},
    )


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> RedirectResponse:
    """Browsers vragen standaard ``/favicon.ico`` op (root) → zonder dit een 404 op
    élke pagina. Verwijs naar het echte static-bestand (permanent, cachebaar)."""
    return RedirectResponse(url="/static/favicon.ico", status_code=301)


@router.get("/sitemap.xml")
def sitemap(request: Request, db: Session = Depends(get_db)) -> Response:
    """Alle publieke personen + projecten als ``application/xml`` sitemap."""
    entries = seo_service.sitemap_entries(db)
    body = request.app.state.templates.get_template("sitemap.xml").render(
        {"request": request, "entries": entries}
    )
    return Response(content=body, media_type="application/xml")


@router.get("/robots.txt")
def robots(request: Request) -> Response:
    """Robots-policy: alleen publieke content indexeerbaar; sitemap-verwijzing."""
    body = request.app.state.templates.get_template("robots.txt").render(
        {"request": request, "base_url": settings.base_url.rstrip("/")}
    )
    return Response(content=body, media_type="text/plain")


_DATA_CACHE = "public, max-age=900"


@router.get("/makers.json")
def makers_json(db: Session = Depends(get_db)) -> JSONResponse:
    """De openbare gids als JSON: alleen openbare profielen, alleen publieke blokken."""
    makers = [directory_service.maker_record(p) for p in directory_service.public_makers(db)]
    return JSONResponse(
        {
            "bron": "dewereldvan.ai — open community van wie in NL/BE met AI werkt",
            "uitleg": "Alleen leden die zelf voor een openbaar profiel kozen. Niet te koop; "
            "volgorde alfabetisch. Contact via de 'contact'-link per maker.",
            "aantal": len(makers),
            "makers": makers,
        },
        headers={"Cache-Control": _DATA_CACHE},
    )


@router.get("/llms.txt")
def llms_txt(request: Request, db: Session = Depends(get_db)) -> Response:
    """Wegwijzer voor AI-assistenten: wat de hub is en waar de data staat."""
    makers = directory_service.public_makers(db)
    body = request.app.state.templates.get_template("llms.txt").render(
        {
            "request": request,
            "base_url": settings.base_url.rstrip("/"),
            "makers": makers,
            "disciplines": directory_service.discipline_counts(makers),
        }
    )
    return Response(
        content=body, media_type="text/plain; charset=utf-8", headers={"Cache-Control": _DATA_CACHE}
    )
